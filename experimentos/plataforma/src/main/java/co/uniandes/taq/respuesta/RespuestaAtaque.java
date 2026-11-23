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

    private final MeterRegistry registro;
    private final RedisClient cliente;
    private final StatefulRedisConnection<String, String> conexionGauge;
    private final HttpClient http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(Duration.ofSeconds(2)).build();
    private final String bloqueoUrl, dbUrl, dbUser, dbPass;
    private final int hilos;
    private final Timer recuperacion, etapaEspera, etapaRevocacion, etapaLiberacion, etapaCancelacion;
    private final Counter liberados, canceladas, revocadas, errores;

    public RespuestaAtaque(MeterRegistry registro,
                           @Value("${taq.redis-url}") String redisUrl, @Value("${taq.bloqueo-url}") String bloqueoUrl,
                           @Value("${taq.db-url}") String dbUrl, @Value("${taq.db-user}") String dbUser,
                           @Value("${taq.db-pass}") String dbPass, @Value("${taq.respuesta-hilos}") int hilos) {
        this.registro = registro;
        this.cliente = RedisClient.create(redisUrl);
        this.conexionGauge = cliente.connect();
        this.bloqueoUrl = bloqueoUrl; this.dbUrl = dbUrl; this.dbUser = dbUser; this.dbPass = dbPass; this.hilos = hilos;
        this.recuperacion = Metricas.timerFino(registro, "taq_recuperacion_seconds");
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
                String crudo = null;
                try {
                    KeyValue<String, String> kv = redis.sync().brpop(1, COLA_ALERTA);
                    if (kv == null || !kv.hasValue()) continue;
                    crudo = kv.getValue();
                    procesar(crudo);
                } catch (Exception e) {
                    errores.increment();
                    log.warn("Error en la respuesta al ataque: {}", e.toString());
                    reencolar(crudo);
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

        @SuppressWarnings("unchecked")
        private void procesar(String crudo) throws Exception {
            long popMs = System.currentTimeMillis();
            Map<String, Object> alerta = Json.mapa(crudo);
            String cuenta = (String) alerta.get("cuenta"), alertaId = (String) alerta.get("id");
            long tsAlerta = ((Number) alerta.get("ts_alerta_ms")).longValue();
            etapaEspera.record(Math.max(0, popMs - tsAlerta), TimeUnit.MILLISECONDS);

            // (a) componente_revocacion_acceso: primero en memoria (Redis); el gateway la lee en ≤ ~1 s y bd_bloqueo la rechaza al instante.
            long t1 = System.nanoTime();
            redis.sync().sadd(REVOCADAS, cuenta);
            long nsRevocacion = System.nanoTime() - t1;
            etapaRevocacion.record(nsRevocacion, TimeUnit.NANOSECONDS);

            // (b) componente_restauracion_estado: liberación en bloque por el índice comprador -> asientos de bd_bloqueo.
            long t2 = System.nanoTime();
            HttpResponse<String> r = http.send(HttpRequest.newBuilder(URI.create(bloqueoUrl + "/bloqueo/liberar-comprador"))
                .timeout(Duration.ofSeconds(10)).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(Json.a(Map.of("comprador", cuenta, "revocar", true, "alertaId", alertaId)))).build(),
                HttpResponse.BodyHandlers.ofString());
            if (r.statusCode() != 200) throw new IllegalStateException("bd_bloqueo respondió " + r.statusCode());
            Map<String, Object> lib = Json.mapa(r.body());
            long nsLiberacion = System.nanoTime() - t2;
            etapaLiberacion.record(nsLiberacion, TimeUnit.NANOSECONDS);
            List<Number> asientos = (List<Number>) lib.getOrDefault("asientos", List.of());
            List<Map<String, Object>> ordenes = (List<Map<String, Object>>) lib.getOrDefault("ordenes", List.of());

            // (c) órdenes canceladas y cuenta revocada, de forma duradera, en una sola transacción.
            long t3 = System.nanoTime();
            long ahora = System.currentTimeMillis();
            if (db == null || db.isClosed()) db = DriverManager.getConnection(dbUrl, dbUser, dbPass);
            db.setAutoCommit(false);
            try {
                try (PreparedStatement ps = db.prepareStatement(
                    "INSERT INTO cuenta_revocada(cuenta, ts_ms, motivo, alerta_id) VALUES (?,?,?,?) ON CONFLICT (cuenta) DO NOTHING")) {
                    ps.setString(1, cuenta); ps.setLong(2, ahora); ps.setString(3, String.valueOf(alerta.get("regla"))); ps.setString(4, alertaId);
                    ps.executeUpdate();
                }
                if (!ordenes.isEmpty()) {
                    try (PreparedStatement ps = db.prepareStatement(
                        "INSERT INTO orden_cancelada(solicitud_id, comprador, asientos, ts_ms, motivo) VALUES (?,?,?,?,?) ON CONFLICT (solicitud_id) DO NOTHING")) {
                        for (Map<String, Object> o : ordenes) {
                            ps.setString(1, (String) o.get("solicitudId")); ps.setString(2, cuenta);
                            ps.setString(3, String.valueOf(o.get("asientos"))); ps.setLong(4, ahora); ps.setString(5, "ATAQUE_REVENTA");
                            ps.addBatch();
                        }
                        ps.executeBatch();
                    }
                }
                db.commit();
            } catch (Exception e) {
                try { db.rollback(); } catch (Exception ignorada) {}
                throw e;
            } finally {
                try { db.setAutoCommit(true); } catch (Exception ignorada) {}
            }
            long nsCancelacion = System.nanoTime() - t3;
            etapaCancelacion.record(nsCancelacion, TimeUnit.NANOSECONDS);

            long finMs = System.currentTimeMillis();
            recuperacion.record(Math.max(0, finMs - tsAlerta), TimeUnit.MILLISECONDS);
            revocadas.increment(); liberados.increment(asientos.size()); canceladas.increment(ordenes.size());
            log.info("RECUPERADO: cuenta={} asientos={} ordenes={} total={} ms (espera {} + {})", cuenta, asientos.size(), ordenes.size(),
                finMs - tsAlerta, popMs - tsAlerta, String.format("revoc %.1f + lib %.1f + cancel %.1f ms",
                    nsRevocacion / 1e6, nsLiberacion / 1e6, nsCancelacion / 1e6));

            // Evidencia de la recuperación (después de contar el tiempo: limpieza definitiva asíncrona).
            Map<String, Object> det = new LinkedHashMap<>();
            det.put("alerta_id", alertaId); det.put("asientos_liberados", asientos); det.put("ordenes_canceladas", ordenes.size());
            det.put("ms_total_desde_alerta", finMs - tsAlerta); det.put("ms_espera_alerta", popMs - tsAlerta);
            det.put("ms_revocacion", nsRevocacion / 1e6); det.put("ms_liberacion", nsLiberacion / 1e6); det.put("ms_cancelacion", nsCancelacion / 1e6);
            det.put("ms_operacion_bd_bloqueo", lib.get("operacion_ms"));
            try (PreparedStatement ps = db.prepareStatement(
                "INSERT INTO auditoria_seguridad(tipo, actor_cuenta, actor_ip, detalle, ts_evento_detector, ts_evidencia) VALUES (?,?,?,?::jsonb,?,?)")) {
                for (String tipo : new String[] {"CUENTA_REVOCADA", "ASIENTOS_LIBERADOS", "ORDENES_CANCELADAS", "RECUPERACION_COMPLETA"}) {
                    ps.setString(1, tipo); ps.setString(2, cuenta); ps.setString(3, String.valueOf(alerta.get("ip")));
                    ps.setString(4, Json.a(det)); ps.setLong(5, tsAlerta); ps.setLong(6, System.currentTimeMillis());
                    ps.addBatch();
                }
                ps.executeBatch();
            }
        }
    }
}
