package co.uniandes.taq.deteccion;

import co.uniandes.taq.comun.EsquemaSeguridad;
import co.uniandes.taq.comun.Json;
import co.uniandes.taq.comun.Metricas;
import io.lettuce.core.KeyValue;
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.annotation.PostConstruct;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * componente_deteccion_ataque (S-1): consume cola_evento_trafico de forma asíncrona (el gateway no espera),
 * mantiene ventanas deslizantes por cuenta y por IP y marca al actor cuyo COMPORTAMIENTO supera el umbral.
 * Al marcar: evidencia en bd_auditoria (Postgres), alerta en cola_alerta_ataque y cuentas de ruido en métricas.
 * El tiempo de S-1 va desde que el evento entra al detector (sale de la cola) hasta que la evidencia queda registrada.
 */
@Component
@ConditionalOnProperty(name = "taq.role", havingValue = "deteccion")
public class DetectorAtaques {
    private static final Logger log = LoggerFactory.getLogger(DetectorAtaques.class);
    public static final String COLA_EVENTO = "cola_evento_trafico", COLA_ALERTA = "cola_alerta_ataque", MARCADAS = "cuentas_marcadas";

    /**
     * Etiqueta del experimento: el GENERADOR declara qué tipo de atacante es (campo tipoAtacante de la solicitud). No es un clasificador:
     * el detector no la usa para decidir si hay ataque, solo la copia a la evidencia, a la alerta y a las métricas.
     * Cualquier valor fuera de esta lista (o ausente) se registra como "sin_etiqueta" para acotar la cardinalidad de las métricas.
     */
    public static final String SIN_ETIQUETA = "sin_etiqueta";
    public static final String[] TIPOS = {"bot_individual", "granja_cuentas", "acaparador", SIN_ETIQUETA};
    public static String etiqueta(Object valor) {
        for (String t : TIPOS) if (t.equals(valor)) return t;
        return SIN_ETIQUETA;
    }

    /** Ventana deslizante de un actor: marcas de tiempo del evento (hora del gateway) y asientos pedidos. */
    static final class Ventana {
        private final ArrayDeque<long[]> eventos = new ArrayDeque<>();   // {ts_ms, asientos}
        private final Map<String, Long> cuentas = new LinkedHashMap<>(); // solo ventanas por IP: cuentas vistas
        private int asientos;
        private volatile long ultimo;

        /** Agrega y devuelve {solicitudes en ventana, asientos en ventana}. */
        synchronized int[] agregar(long ts, int nAsientos, long ventanaMs, String cuenta) {
            eventos.addLast(new long[] {ts, nAsientos});
            asientos += nAsientos;
            if (cuenta != null) cuentas.put(cuenta, ts);
            expirar(ts - ventanaMs);
            ultimo = Math.max(ultimo, ts);
            return new int[] {eventos.size(), asientos};
        }
        private void expirar(long limite) {
            while (!eventos.isEmpty() && eventos.peekFirst()[0] < limite) asientos -= (int) eventos.pollFirst()[1];
            if (!cuentas.isEmpty()) cuentas.values().removeIf(t -> t < limite);
        }
        synchronized List<String> cuentasVistas() { return new ArrayList<>(cuentas.keySet()); }
    }

    private final MeterRegistry registro;
    private final RedisClient cliente;
    private final StatefulRedisConnection<String, String> conexionGauge;
    private final Parametros parametros;
    private final String dbUrl, dbUser, dbPass;
    private final int hilos;
    private final String prefijoBot;       // instrumentación del experimento (no de la detección): cuentas de bots conocidas por su prefijo
    private final Map<String, Ventana> porCuenta = new ConcurrentHashMap<>();
    private final Map<String, Ventana> porIp = new ConcurrentHashMap<>();
    private final Map<String, Long> marcadas = new ConcurrentHashMap<>();       // cuenta -> ms de la marca
    private final Map<String, String> etiquetaCuenta = new ConcurrentHashMap<>();   // última etiqueta vista por cuenta (para las marcas en bloque por IP)
    private final Set<String> ipMarcadas = ConcurrentHashMap.newKeySet();

    private final Timer esperaCola;
    private final Map<String, Timer> deteccionPorTipo = new HashMap<>();
    private final DistributionSummary antesDeMarca;
    private final Counter falsosPositivos, sospechosas, postMarca, procesados, errores, descartados;

    public DetectorAtaques(MeterRegistry registro, Parametros parametros,
                           @Value("${taq.redis-url}") String redisUrl,
                           @Value("${taq.db-url}") String dbUrl, @Value("${taq.db-user}") String dbUser,
                           @Value("${taq.db-pass}") String dbPass, @Value("${taq.deteccion-hilos}") int hilos,
                           @Value("${taq.oraculo-prefijo-bot:bot-}") String prefijoBot) {
        this.prefijoBot = prefijoBot;
        this.registro = registro;
        this.parametros = parametros;
        this.cliente = RedisClient.create(redisUrl);
        this.conexionGauge = cliente.connect();
        this.dbUrl = dbUrl; this.dbUser = dbUser; this.dbPass = dbPass; this.hilos = hilos;
        // Un histograma por etiqueta (4 valores fijos): las consultas agregadas por (le) siguen valiendo.
        for (String t : TIPOS) deteccionPorTipo.put(t, Metricas.timerFino(registro, "taq_deteccion_seconds", "tipo", t));
        this.esperaCola = Metricas.timerFino(registro, "taq_evento_trafico_espera_seconds");
        this.antesDeMarca = DistributionSummary.builder("taq_solicitudes_fraudulentas_antes_de_marca")
            .serviceLevelObjectives(1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50).register(registro);
        // Solo para medir el experimento: una cuenta marcada que NO lleva el prefijo de los bots es un comprador legítimo marcado.
        this.falsosPositivos = Counter.builder("taq_marcas_falsos_positivos_total").register(registro);
        this.sospechosas = Counter.builder("taq_cuentas_sospechosas_total").register(registro);
        this.postMarca = Counter.builder("taq_solicitudes_fraudulentas_post_marca_total").register(registro);
        this.procesados = Counter.builder("taq_eventos_procesados_total").register(registro);
        this.errores = Counter.builder("taq_deteccion_errores_total").register(registro);
        this.descartados = Counter.builder("taq_eventos_malformados_total").register(registro);
        registro.gauge("taq_cola_evento_trafico_profundidad", conexionGauge, c -> {
            try { return c.sync().llen(COLA_EVENTO); } catch (Exception e) { return -1; }
        });
        registro.gauge("taq_ventanas_cuenta_activas", porCuenta, Map::size);
    }

    @PostConstruct
    void iniciar() {
        try (Connection db = DriverManager.getConnection(dbUrl, dbUser, dbPass)) {
            EsquemaSeguridad.crear(db);
        } catch (Exception e) {
            log.error("No se pudo crear el esquema de seguridad (se reintenta al marcar): {}", e.toString());
        }
        for (int i = 0; i < hilos; i++) {
            Thread t = new Thread(new Trabajador(), "deteccion-" + i);
            t.setDaemon(true);
            t.start();
        }
        Thread limpieza = new Thread(() -> {
            while (true) {
                try { Thread.sleep(5000); } catch (InterruptedException ie) { return; }
                long limite = System.currentTimeMillis() - 2L * parametros.reglas().ventanaS() * 1000L;
                porCuenta.values().removeIf(v -> v.ultimo < limite);
                porIp.values().removeIf(v -> v.ultimo < limite);
            }
        }, "deteccion-limpieza");
        limpieza.setDaemon(true);
        limpieza.start();
        log.info("componente_deteccion_ataque listo: {} hilos, reglas {}", hilos, parametros.reglas().mapa());
    }

    /** Un hilo de consumo con su propia conexión a Redis y a Postgres. */
    private final class Trabajador implements Runnable {
        private StatefulRedisConnection<String, String> redis;
        private Connection db;

        @Override public void run() {
            redis = cliente.connect();
            try { db = DriverManager.getConnection(dbUrl, dbUser, dbPass); } catch (Exception e) { log.warn("Postgres aún no disponible: {}", e.toString()); }
            while (true) {
                try {
                    KeyValue<String, String> kv = redis.sync().brpop(1, COLA_EVENTO);
                    if (kv == null || !kv.hasValue()) continue;
                    long entradaNs = System.nanoTime();          // el evento ENTRA al detector
                    long entradaMs = System.currentTimeMillis();
                    evaluar(kv.getValue(), entradaNs, entradaMs);
                } catch (Exception e) {
                    errores.increment();
                    log.warn("Error en el detector: {}", e.toString());
                    try { Thread.sleep(100); } catch (InterruptedException ie) { return; }
                }
            }
        }

        @SuppressWarnings("unchecked")
        private void evaluar(String crudo, long entradaNs, long entradaMs) throws Exception {
            Map<String, Object> m;
            try { m = Json.mapa(crudo); } catch (RuntimeException e) { descartados.increment(); return; }
            String cuenta = String.valueOf(m.get("cuenta")), ip = String.valueOf(m.get("ip")), ruta = String.valueOf(m.get("ruta"));
            long ts = ((Number) m.get("ts_ms")).longValue();
            int nAs = m.get("asientos") instanceof List<?> l ? l.size() : 0;
            boolean porXff = "xff".equals(m.get("ip_fuente"));
            String tipoAt = etiqueta(m.get("tipo_atacante"));   // solo metadato del experimento
            if (!SIN_ETIQUETA.equals(tipoAt)) etiquetaCuenta.put(cuenta, tipoAt);   // solo los atacantes etiquetados (acotado)
            procesados.increment();
            esperaCola.record(Math.max(0, entradaMs - ts), TimeUnit.MILLISECONDS);
            if (marcadas.containsKey(cuenta)) { postMarca.increment(); return; }   // ya marcada: lo que sigue pasó tras la marca
            Parametros.Reglas r = parametros.reglas();
            long ventanaMs = r.ventanaS() * 1000L;

            // Regla 1 (comportamiento de la cuenta): solicitudes de reserva y asientos pedidos en la ventana.
            if ("reservar".equals(ruta)) {
                int[] c = porCuenta.computeIfAbsent(cuenta, k -> new Ventana()).agregar(ts, nAs, ventanaMs, null);
                if (r.umbralCuenta() > 0 && c[0] >= r.umbralCuenta()) {
                    marcar(List.of(cuenta), ip, "cuenta_frecuencia", c[0], c[1], r.umbralCuenta(), ventanaMs, entradaNs, entradaMs); return;
                }
                if (r.umbralAsientos() > 0 && c[1] > r.umbralAsientos()) {
                    marcar(List.of(cuenta), ip, "cuenta_asientos", c[0], c[1], r.umbralAsientos(), ventanaMs, entradaNs, entradaMs); return;
                }
            }
            // Regla 2 (comportamiento de la IP): solo con IP de cliente real (X-Forwarded-For); la IP remota es la del balanceador.
            if (porXff && r.umbralIp() > 0) {
                if (ipMarcadas.contains(ip)) {
                    marcar(List.of(cuenta), ip, "ip_marcada", 1, nAs, r.umbralIp(), ventanaMs, entradaNs, entradaMs); return;
                }
                Ventana v = porIp.computeIfAbsent(ip, k -> new Ventana());
                int[] c = v.agregar(ts, nAs, ventanaMs, cuenta);
                if (c[0] >= r.umbralIp()) {
                    ipMarcadas.add(ip);
                    // v2: todas las cuentas vistas tras la IP se marcan en UN lote (una escritura de evidencia, una alerta en bloque).
                    marcar(v.cuentasVistas(), ip, "ip_frecuencia", c[0], c[1], r.umbralIp(), ventanaMs, entradaNs, entradaMs);
                }
            }
        }

        /**
         * Marca una o varias cuentas con la misma regla (v2: marca en lote). Orden: (a) decidir cuáles son nuevas (memoria local y conjunto
         * Redis cuentas_marcadas, en un solo viaje en pipeline); (b) evidencia de TODAS en un único INSERT multifila contra bd_auditoria;
         * (c) solo DESPUÉS de escrita la evidencia: métricas, alertas (un solo LPUSH) y una línea de log por lote.
         * El histograma taq_deteccion_seconds{tipo} sigue midiendo, por cuenta, desde que el evento ENTRA al detector hasta que su evidencia
         * quedó escrita. Con una sola cuenta el comportamiento es el de siempre.
         */
        private void marcar(List<String> candidatas, String ip, String regla, int solicitudes, int asientos, int umbral, long ventanaMs,
                            long entradaNs, long entradaMs) throws Exception {
            List<String> nuevas = new ArrayList<>(candidatas.size());
            for (String c : candidatas) if (marcadas.putIfAbsent(c, entradaMs) == null) nuevas.add(c);
            if (nuevas.isEmpty()) return;
            List<String> cuentas = new ArrayList<>(nuevas.size());
            if (nuevas.size() == 1) {
                if (redis.sync().sadd(MARCADAS, nuevas.get(0)) != 0) cuentas.add(nuevas.get(0));    // otra réplica ya la marcó si es 0
            } else {                                                                                   // pipeline: un solo viaje de ida y vuelta
                List<io.lettuce.core.RedisFuture<Long>> fs = new ArrayList<>(nuevas.size());
                redis.setAutoFlushCommands(false);
                try {
                    for (String c : nuevas) fs.add(redis.async().sadd(MARCADAS, c));
                    redis.flushCommands();
                } finally { redis.setAutoFlushCommands(true); }
                for (int i = 0; i < fs.size(); i++) if (fs.get(i).get(5, TimeUnit.SECONDS) != 0) cuentas.add(nuevas.get(i));
            }
            if (cuentas.isEmpty()) return;
            int n = cuentas.size();
            String[] tipos = new String[n];
            for (int i = 0; i < n; i++) tipos[i] = etiquetaCuenta.getOrDefault(cuentas.get(i), SIN_ETIQUETA);
            if (!prefijoBot.isEmpty()) for (String c : cuentas) if (!c.startsWith(prefijoBot)) falsosPositivos.increment();
            // Evidencia en bd_auditoria (S-1: el reloj se detiene cuando queda registrada). Un INSERT multifila para todo el lote.
            boolean ok = false;
            for (int intento = 0; intento < 2 && !ok; intento++) {
                try {
                    if (db == null || db.isClosed()) { db = DriverManager.getConnection(dbUrl, dbUser, dbPass); EsquemaSeguridad.crear(db); }
                    StringBuilder sql = new StringBuilder("INSERT INTO auditoria_seguridad(tipo, actor_cuenta, actor_ip, detalle, ts_evento_detector, ts_evidencia, tipo_atacante) VALUES ");
                    for (int i = 0; i < n; i++) sql.append(i == 0 ? "" : ",").append("('ATAQUE_DETECTADO', ?, ?, ?::jsonb, ?, ?, ?)");
                    try (PreparedStatement ps = db.prepareStatement(sql.toString())) {
                        long ahoraEv = System.currentTimeMillis();
                        int k = 1;
                        for (int i = 0; i < n; i++) {
                            Map<String, Object> detalle = new LinkedHashMap<>();
                            detalle.put("regla", regla); detalle.put("tipo_atacante", tipos[i]); detalle.put("solicitudes_en_ventana", solicitudes);
                            detalle.put("asientos_en_ventana", asientos); detalle.put("umbral", umbral);
                            detalle.put("ventana_s", ventanaMs / 1000);
                            if (n > 1) detalle.put("lote", n);
                            ps.setString(k++, cuentas.get(i)); ps.setString(k++, ip); ps.setString(k++, Json.a(detalle));
                            ps.setLong(k++, entradaMs); ps.setLong(k++, ahoraEv); ps.setString(k++, tipos[i]);
                        }
                        ps.executeUpdate();
                    }
                    ok = true;
                } catch (Exception e) {
                    errores.increment();
                    log.warn("No se pudo registrar la evidencia ({} cuentas, p. ej. {}): {}", n, cuentas.get(0), e.toString());
                    try { if (db != null) db.close(); } catch (Exception ignorada) {}
                    db = null;
                }
            }
            long duracionNs = System.nanoTime() - entradaNs;     // evidencia ya escrita: de aquí en adelante no cuenta para S-1
            // (c) métricas, alertas y log, después de la evidencia.
            sospechosas.increment(n);
            Map<String, Integer> porTipo = new LinkedHashMap<>();
            for (String t : tipos) porTipo.merge(t, 1, Integer::sum);
            for (var e : porTipo.entrySet()) {
                if (ok) { Timer tm = deteccionPorTipo.get(e.getKey()); for (int i = 0; i < e.getValue(); i++) tm.record(duracionNs, TimeUnit.NANOSECONDS); }
                contador(regla, e.getKey()).increment(e.getValue());
            }
            for (int i = 0; i < n; i++) antesDeMarca.record(solicitudes);
            long ahoraAlerta = System.currentTimeMillis();
            String[] alertas = new String[n];
            for (int i = 0; i < n; i++) {
                Map<String, Object> alerta = new LinkedHashMap<>();
                alerta.put("id", UUID.randomUUID().toString()); alerta.put("cuenta", cuentas.get(i)); alerta.put("ip", ip);
                alerta.put("regla", regla); alerta.put("tipo_atacante", tipos[i]); alerta.put("ts_evento_detector_ms", entradaMs);
                alerta.put("ts_alerta_ms", ahoraAlerta); alerta.put("solicitudes_antes_de_marca", solicitudes);
                alertas[i] = Json.a(alerta);
            }
            redis.sync().lpush(COLA_ALERTA, alertas);          // un solo comando para todo el lote
            if (n == 1) log.info("ATAQUE detectado: cuenta={} ip={} tipo_atacante={} regla={} solicitudes={} deteccion={} ms", cuentas.get(0), ip, tipos[0], regla, solicitudes,
                String.format("%.1f", duracionNs / 1e6));
            else log.info("ATAQUE detectado en lote: {} cuentas ip={} tipos={} regla={} solicitudes={} deteccion={} ms (evidencia en un INSERT)", n, ip, porTipo, regla, solicitudes,
                String.format("%.1f", duracionNs / 1e6));
        }
    }

    private final Map<String, Counter> contadores = new ConcurrentHashMap<>();
    private Counter contador(String regla, String tipo) {
        return contadores.computeIfAbsent(regla + "|" + tipo, k -> Counter.builder("taq_ataques_detectados_total").tag("regla", regla).tag("tipo", tipo).register(registro));
    }
}
