package co.uniandes.taq.respuesta;

import co.uniandes.taq.comun.EsquemaSeguridad;
import co.uniandes.taq.comun.Json;
import co.uniandes.taq.comun.Metricas;
import io.lettuce.core.KeyValue;
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.annotation.PostConstruct;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * componente_respuesta_ataque (S-2) con componente_revocacion_acceso y componente_restauracion_estado.
 * Por cada alerta de cola_alerta_ataque: (a) revoca la cuenta, (b) libera sus asientos retenidos con el índice en memoria
 * de bd_bloqueo y (c) cancela sus órdenes. El tiempo de S-2 va desde la alerta hasta que las tres cosas están hechas
 * (revocación en Redis y Postgres, liberación en memoria y órdenes canceladas en Postgres). La evidencia de la
 * recuperación en bd_auditoria se escribe DESPUÉS (limpieza asíncrona, fuera de los 300 ms, como dice el ASR).
 */
@Component
@ConditionalOnProperty(name = "taq.role", havingValue = "respuesta")
public class RespuestaAtaque {
    private static final Logger log = LoggerFactory.getLogger(RespuestaAtaque.class);
    public static final String COLA_ALERTA = "cola_alerta_ataque", REVOCADAS = "cuentas_revocadas";
    private static final Object POP = new Object();
    private static final int LOTE_MAX = 200;   // alertas que se recuperan en un solo lote

    private final MeterRegistry registro;
    private final RedisClient cliente;
    private final StatefulRedisConnection<String, String> conexionGauge;
    private final HttpClient http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(Duration.ofSeconds(2)).build();
    private final String bloqueoUrl, dbUrl, dbUser, dbPass;
    private final int hilos;
    private final Map<String, Timer> recuperacionPorTipo = new java.util.HashMap<>();
    private final Timer etapaEspera, etapaRevocacion, etapaLiberacion, etapaCancelacion;
    private final Counter liberados, canceladas, revocadas, errores;

    public RespuestaAtaque(MeterRegistry registro,
                           @Value("${taq.redis-url}") String redisUrl, @Value("${taq.bloqueo-url}") String bloqueoUrl,
                           @Value("${taq.db-url}") String dbUrl, @Value("${taq.db-user}") String dbUser,
                           @Value("${taq.db-pass}") String dbPass, @Value("${taq.respuesta-hilos}") int hilos) {
        this.registro = registro;
        this.cliente = RedisClient.create(redisUrl);
        this.conexionGauge = cliente.connect();
        this.bloqueoUrl = bloqueoUrl; this.dbUrl = dbUrl; this.dbUser = dbUser; this.dbPass = dbPass; this.hilos = hilos;
        // Un timer por tipo de ataque (etiqueta "tipo"; solo 3 valores + desconocido).
        for (String t : new String[] {"bot_individual", "granja_cuentas", "acaparador", "sin_etiqueta"})
            recuperacionPorTipo.put(t, Metricas.timerFino(registro, "taq_recuperacion_seconds", "tipo", t));
        this.etapaEspera = Metricas.timerFino(registro, "taq_recuperacion_etapa_seconds", "etapa", "espera_alerta");
        this.etapaRevocacion = Metricas.timerFino(registro, "taq_recuperacion_etapa_seconds", "etapa", "revocacion_redis");
        this.etapaLiberacion = Metricas.timerFino(registro, "taq_recuperacion_etapa_seconds", "etapa", "liberacion_asientos");
        this.etapaCancelacion = Metricas.timerFino(registro, "taq_recuperacion_etapa_seconds", "etapa", "cancelacion_y_cuenta_postgres");
        this.liberados = Counter.builder("taq_asientos_liberados_total").register(registro);
        this.canceladas = Counter.builder("taq_ordenes_canceladas_total").register(registro);
        this.revocadas = Counter.builder("taq_cuentas_revocadas_total").register(registro);
        this.errores = Counter.builder("taq_respuesta_errores_total").register(registro);
        registro.gauge("taq_cola_alerta_profundidad", conexionGauge, c -> {
            try { return c.sync().llen(COLA_ALERTA); } catch (Exception e) { return -1; }
        });
    }

    @PostConstruct
    void iniciar() {
        try (Connection db = DriverManager.getConnection(dbUrl, dbUser, dbPass)) {
            EsquemaSeguridad.crear(db);
        } catch (Exception e) {
            log.error("No se pudo crear el esquema de seguridad: {}", e.toString());
        }
        for (int i = 0; i < hilos; i++) {
            Thread t = new Thread(new Trabajador(), "respuesta-" + i);
            t.setDaemon(true);
            t.start();
        }
        log.info("componente_respuesta_ataque listo: {} hilos", hilos);
    }

    private final class Trabajador implements Runnable {
        private StatefulRedisConnection<String, String> redis;
        private Connection db;

        @Override public void run() {
            redis = cliente.connect();
            calentar();
            while (true) {
                List<String> lote = null;
                try {
                    // Un solo hilo a la vez espera y drena: la ráfaga de una granja (un LPUSH de N alertas) cae entera en UN lote
                    // y no se reparte entre hilos que luego harían cola en el hilo único de bd_bloqueo.
                    synchronized (POP) {
                        KeyValue<String, String> kv = redis.sync().brpop(1, COLA_ALERTA);
                        if (kv == null || !kv.hasValue()) continue;
                        lote = new ArrayList<>();
                        lote.add(kv.getValue());
                        drenar(lote);          // v2: ráfaga de alertas (p. ej. toda una granja) -> un solo lote
                    }
                    procesarLote(lote);
                    lote = null;
                } catch (Exception e) {
                    errores.increment();
                    log.warn("Error en la respuesta al ataque: {}", e.toString());
                    if (lote != null) for (String a : lote) reencolar(a);
                    try { if (db != null) db.close(); } catch (Exception ignorada) {}
                    db = null;
                    try { Thread.sleep(100); } catch (InterruptedException ie) { return; }
                }
            }
        }

        /** Abre la conexión a Postgres y la de HTTP hacia bd_bloqueo antes de la primera alerta (que no pague el arranque en frío). */
        private void calentar() {
            for (int i = 0; i < 30; i++) {
                try {
                    if (db == null || db.isClosed()) db = DriverManager.getConnection(dbUrl, dbUser, dbPass);
                    try (var st = db.createStatement()) { st.execute("SELECT 1"); }
                    http.send(HttpRequest.newBuilder(URI.create(bloqueoUrl + "/bloqueo/retenidos?compradores=_calentamiento"))
                        .timeout(Duration.ofSeconds(5)).GET().build(), HttpResponse.BodyHandlers.ofString());
                    return;
                } catch (Exception e) {
                    try { Thread.sleep(1000); } catch (InterruptedException ie) { return; }
                }
            }
        }

        /** Si algo falla (bd_bloqueo o Postgres caídos) la alerta vuelve a la cola, hasta 3 intentos. */
        private void reencolar(String crudo) {
            if (crudo == null) return;
            try {
                Map<String, Object> a = Json.mapa(crudo);
                int intentos = a.get("intentos") instanceof Number n ? n.intValue() : 0;
                if (intentos >= 3) { log.error("Alerta descartada tras 3 intentos: {}", crudo); return; }
                a.put("intentos", intentos + 1);
                redis.sync().lpush(COLA_ALERTA, Json.a(a));
            } catch (Exception e) { log.error("No se pudo reencolar la alerta: {}", e.toString()); }
        }

        /** Saca de la cola, sin esperar, hasta LOTE_MAX-1 alertas más (RPOP con cuenta; si el Redis no lo soporta, se procesa de a una). */
        private void drenar(List<String> lote) {
            try {
                List<String> mas = redis.sync().rpop(COLA_ALERTA, LOTE_MAX - 1);
                if (mas != null) lote.addAll(mas);
            } catch (Exception e) { log.debug("No se pudo drenar la cola de alertas por lote: {}", e.toString()); }
        }

        /** Multifila en tandas: INSERT INTO t(cols) VALUES (?,..),(?,..) [sufijo]. */
        private void insertarFilas(String cabecera, int columnas, String sufijo, List<Object[]> filas) throws Exception {
            final int tanda = 400;
            String grupo = "(" + "?,".repeat(columnas - 1) + "?)";
            for (int i = 0; i < filas.size(); i += tanda) {
                List<Object[]> parte = filas.subList(i, Math.min(filas.size(), i + tanda));
                StringBuilder sql = new StringBuilder(cabecera).append(" VALUES ");
                for (int j = 0; j < parte.size(); j++) sql.append(j == 0 ? "" : ",").append(grupo);
                sql.append(sufijo);
                try (PreparedStatement ps = db.prepareStatement(sql.toString())) {
                    int k = 1;
                    for (Object[] f : parte) for (Object v : f) ps.setObject(k++, v);
                    ps.executeUpdate();
                }
            }
        }

        /**
         * v2: recupera un LOTE de alertas. Por cuenta, el tiempo de S-2 sigue yendo desde SU alerta hasta que sus asientos están liberados,
         * sus órdenes canceladas y la cuenta revocada; pero las tres cosas se hacen en bloque: un SADD múltiple, UNA operación del hilo
         * único de bd_bloqueo y una transacción de Postgres con inserciones multifila. La evidencia posterior va después (fuera del tiempo).
         */
        @SuppressWarnings("unchecked")
        private void procesarLote(List<String> crudos) throws Exception {
            long popMs = System.currentTimeMillis();
            int n = crudos.size();
            List<Map<String, Object>> alertas = new ArrayList<>(n);
            for (String c : crudos) alertas.add(Json.mapa(c));
            String[] cuentas = new String[n], tipos = new String[n], ids = new String[n];
            long[] tsAlerta = new long[n];
            for (int i = 0; i < n; i++) {
                Map<String, Object> a = alertas.get(i);
                cuentas[i] = (String) a.get("cuenta"); ids[i] = (String) a.get("id");
                tsAlerta[i] = ((Number) a.get("ts_alerta_ms")).longValue();
                String t = String.valueOf(a.getOrDefault("tipo_atacante", "sin_etiqueta"));
                tipos[i] = recuperacionPorTipo.containsKey(t) ? t : "sin_etiqueta";
                etapaEspera.record(Math.max(0, popMs - tsAlerta[i]), TimeUnit.MILLISECONDS);
            }

            // (a) componente_revocacion_acceso: un solo SADD con todas las cuentas.
            long t1 = System.nanoTime();
            redis.sync().sadd(REVOCADAS, cuentas);
            long nsRevocacion = System.nanoTime() - t1;

            // (b) componente_restauracion_estado: UNA operación del hilo único libera a todos los compradores del lote.
            long t2 = System.nanoTime();
            HttpResponse<String> r = http.send(HttpRequest.newBuilder(URI.create(bloqueoUrl + "/bloqueo/liberar-compradores"))
                .timeout(Duration.ofSeconds(10)).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(Json.a(Map.of("compradores", List.of(cuentas), "revocar", true)))).build(),
                HttpResponse.BodyHandlers.ofString());
            if (r.statusCode() != 200) throw new IllegalStateException("bd_bloqueo respondió " + r.statusCode());
            Map<String, Object> lib = Json.mapa(r.body());
            long nsLiberacion = System.nanoTime() - t2;
            List<Map<String, Object>> resultados = (List<Map<String, Object>>) lib.get("resultados");
            if (resultados == null || resultados.size() != n) throw new IllegalStateException("bd_bloqueo devolvió un lote incompleto");

            // (c) órdenes canceladas y cuentas revocadas, de forma duradera, en una sola transacción con inserciones multifila.
            long t3 = System.nanoTime();
            long ahora = System.currentTimeMillis();
            if (db == null || db.isClosed()) db = DriverManager.getConnection(dbUrl, dbUser, dbPass);
            List<Object[]> filasCuenta = new ArrayList<>(n), filasOrden = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                filasCuenta.add(new Object[] {cuentas[i], ahora, String.valueOf(alertas.get(i).get("regla")), ids[i]});
                for (Map<String, Object> o : (List<Map<String, Object>>) resultados.get(i).getOrDefault("ordenes", List.of()))
                    filasOrden.add(new Object[] {o.get("solicitudId"), cuentas[i], String.valueOf(o.get("asientos")), ahora, "ATAQUE_REVENTA"});
            }
            db.setAutoCommit(false);
            try {
                insertarFilas("INSERT INTO cuenta_revocada(cuenta, ts_ms, motivo, alerta_id)", 4, " ON CONFLICT (cuenta) DO NOTHING", filasCuenta);
                if (!filasOrden.isEmpty())
                    insertarFilas("INSERT INTO orden_cancelada(solicitud_id, comprador, asientos, ts_ms, motivo)", 5, " ON CONFLICT (solicitud_id) DO NOTHING", filasOrden);
                db.commit();
            } catch (Exception e) {
                try { db.rollback(); } catch (Exception ignorada) {}
                throw e;
            } finally {
                try { db.setAutoCommit(true); } catch (Exception ignorada) {}
            }
            long nsCancelacion = System.nanoTime() - t3;

            long finMs = System.currentTimeMillis();
            int totAsientos = 0, totOrdenes = 0;
            for (int i = 0; i < n; i++) {
                List<Number> as = (List<Number>) resultados.get(i).getOrDefault("asientos", List.of());
                List<?> os = (List<?>) resultados.get(i).getOrDefault("ordenes", List.of());
                totAsientos += as.size(); totOrdenes += os.size();
                // por cuenta: desde SU alerta hasta que las tres cosas están hechas
                recuperacionPorTipo.get(tipos[i]).record(Math.max(0, finMs - tsAlerta[i]), TimeUnit.MILLISECONDS);
                etapaRevocacion.record(nsRevocacion, TimeUnit.NANOSECONDS);
                etapaLiberacion.record(nsLiberacion, TimeUnit.NANOSECONDS);
                etapaCancelacion.record(nsCancelacion, TimeUnit.NANOSECONDS);
            }
            revocadas.increment(n); liberados.increment(totAsientos); canceladas.increment(totOrdenes);
            long maxDesdeAlerta = 0; for (int i = 0; i < n; i++) maxDesdeAlerta = Math.max(maxDesdeAlerta, finMs - tsAlerta[i]);
            log.info("RECUPERADO lote de {} cuentas: asientos={} ordenes={} max desde alerta={} ms (espera + revoc {} + lib {} + cancel {} ms)", n, totAsientos, totOrdenes,
                maxDesdeAlerta, String.format("%.1f", nsRevocacion / 1e6), String.format("%.1f", nsLiberacion / 1e6), String.format("%.1f", nsCancelacion / 1e6));

            // Evidencia de la recuperación (después de contar el tiempo: limpieza definitiva asíncrona), también en lote.
            List<Object[]> evidencia = new ArrayList<>(n * 4);
            long ahoraEv = System.currentTimeMillis();
            for (int i = 0; i < n; i++) {
                List<Number> as = (List<Number>) resultados.get(i).getOrDefault("asientos", List.of());
                Map<String, Object> det = new LinkedHashMap<>();
                det.put("alerta_id", ids[i]); det.put("tipo_atacante", tipos[i]); det.put("asientos_liberados", as);
                det.put("ordenes_canceladas", ((List<?>) resultados.get(i).getOrDefault("ordenes", List.of())).size());
                det.put("ms_total_desde_alerta", finMs - tsAlerta[i]); det.put("ms_espera_alerta", popMs - tsAlerta[i]);
                det.put("ms_revocacion", nsRevocacion / 1e6); det.put("ms_liberacion", nsLiberacion / 1e6); det.put("ms_cancelacion", nsCancelacion / 1e6);
                det.put("ms_operacion_bd_bloqueo", lib.get("operacion_ms")); det.put("lote", n);
                String detalle = Json.a(det);
                for (String tipo : new String[] {"CUENTA_REVOCADA", "ASIENTOS_LIBERADOS", "ORDENES_CANCELADAS", "RECUPERACION_COMPLETA"})
                    evidencia.add(new Object[] {tipo, cuentas[i], String.valueOf(alertas.get(i).get("ip")), detalle, tsAlerta[i], ahoraEv, tipos[i]});
            }
            for (int i = 0; i < evidencia.size(); i += 400) {
                // detalle es JSONB: se castea en la consulta
                List<Object[]> parte = evidencia.subList(i, Math.min(evidencia.size(), i + 400));
                StringBuilder sql = new StringBuilder("INSERT INTO auditoria_seguridad(tipo, actor_cuenta, actor_ip, detalle, ts_evento_detector, ts_evidencia, tipo_atacante) VALUES ");
                for (int j = 0; j < parte.size(); j++) sql.append(j == 0 ? "" : ",").append("(?,?,?,?::jsonb,?,?,?)");
                try (PreparedStatement ps = db.prepareStatement(sql.toString())) {
                    int k = 1;
                    for (Object[] f : parte) for (Object v : f) ps.setObject(k++, v);
                    ps.executeUpdate();
                }
            }
        }
    }
}
