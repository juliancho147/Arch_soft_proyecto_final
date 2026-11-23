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
    private final Set<String> ipMarcadas = ConcurrentHashMap.newKeySet();

    private final Timer deteccion, esperaCola;
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
        this.deteccion = Metricas.timerFino(registro, "taq_deteccion_seconds");
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
            procesados.increment();
            esperaCola.record(Math.max(0, entradaMs - ts), TimeUnit.MILLISECONDS);
            if (marcadas.containsKey(cuenta)) { postMarca.increment(); return; }   // ya marcada: lo que sigue pasó tras la marca
            Parametros.Reglas r = parametros.reglas();
            long ventanaMs = r.ventanaS() * 1000L;

            // Regla 1 (comportamiento de la cuenta): solicitudes de reserva y asientos pedidos en la ventana.
            if ("reservar".equals(ruta)) {
                int[] c = porCuenta.computeIfAbsent(cuenta, k -> new Ventana()).agregar(ts, nAs, ventanaMs, null);
                if (r.umbralCuenta() > 0 && c[0] >= r.umbralCuenta()) {
                    marcar(cuenta, ip, "cuenta_frecuencia", c[0], c[1], r.umbralCuenta(), ventanaMs, entradaNs, entradaMs); return;
                }
                if (r.umbralAsientos() > 0 && c[1] > r.umbralAsientos()) {
                    marcar(cuenta, ip, "cuenta_asientos", c[0], c[1], r.umbralAsientos(), ventanaMs, entradaNs, entradaMs); return;
                }
            }
            // Regla 2 (comportamiento de la IP): solo con IP de cliente real (X-Forwarded-For); la IP remota es la del balanceador.
            if (porXff && r.umbralIp() > 0) {
                if (ipMarcadas.contains(ip)) {
                    marcar(cuenta, ip, "ip_marcada", 1, nAs, r.umbralIp(), ventanaMs, entradaNs, entradaMs); return;
                }
                Ventana v = porIp.computeIfAbsent(ip, k -> new Ventana());
                int[] c = v.agregar(ts, nAs, ventanaMs, cuenta);
                if (c[0] >= r.umbralIp()) {
                    ipMarcadas.add(ip);
                    for (String cu : v.cuentasVistas())
                        marcar(cu, ip, "ip_frecuencia", c[0], c[1], r.umbralIp(), ventanaMs, entradaNs, entradaMs);
                }
            }
        }

        private void marcar(String cuenta, String ip, String regla, int solicitudes, int asientos, int umbral, long ventanaMs,
                            long entradaNs, long entradaMs) throws Exception {
            if (marcadas.putIfAbsent(cuenta, entradaMs) != null) return;
            if (redis.sync().sadd(MARCADAS, cuenta) == 0) return;       // otra réplica del detector ya la marcó
            sospechosas.increment();
            if (!prefijoBot.isEmpty() && !cuenta.startsWith(prefijoBot)) falsosPositivos.increment();
            Map<String, Object> detalle = new LinkedHashMap<>();
            detalle.put("regla", regla); detalle.put("solicitudes_en_ventana", solicitudes);
            detalle.put("asientos_en_ventana", asientos); detalle.put("umbral", umbral);
            detalle.put("ventana_s", ventanaMs / 1000);
            // Evidencia en bd_auditoria (S-1: el reloj se detiene cuando queda registrada).
            boolean ok = false;
            for (int intento = 0; intento < 2 && !ok; intento++) {
                try {
                    if (db == null || db.isClosed()) { db = DriverManager.getConnection(dbUrl, dbUser, dbPass); EsquemaSeguridad.crear(db); }
                    try (PreparedStatement ps = db.prepareStatement(
                        "INSERT INTO auditoria_seguridad(tipo, actor_cuenta, actor_ip, detalle, ts_evento_detector, ts_evidencia) "
                        + "VALUES ('ATAQUE_DETECTADO', ?, ?, ?::jsonb, ?, ?)")) {
                        ps.setString(1, cuenta); ps.setString(2, ip); ps.setString(3, Json.a(detalle));
                        ps.setLong(4, entradaMs); ps.setLong(5, System.currentTimeMillis());
                        ps.executeUpdate();
                    }
                    ok = true;
                } catch (Exception e) {
                    errores.increment();
                    log.warn("No se pudo registrar la evidencia ({}): {}", cuenta, e.toString());
                    try { if (db != null) db.close(); } catch (Exception ignorada) {}
                    db = null;
                }
            }
            long duracionNs = System.nanoTime() - entradaNs;
            if (ok) deteccion.record(duracionNs, TimeUnit.NANOSECONDS);
            Counter.builder("taq_ataques_detectados_total").tag("regla", regla).register(registro).increment();
            antesDeMarca.record(solicitudes);
            // Alerta para componente_respuesta_ataque (después de la evidencia; no frena a nadie).
            Map<String, Object> alerta = new LinkedHashMap<>();
            alerta.put("id", UUID.randomUUID().toString()); alerta.put("cuenta", cuenta); alerta.put("ip", ip);
            alerta.put("regla", regla); alerta.put("ts_evento_detector_ms", entradaMs);
            alerta.put("ts_alerta_ms", System.currentTimeMillis()); alerta.put("solicitudes_antes_de_marca", solicitudes);
            redis.sync().lpush(COLA_ALERTA, Json.a(alerta));
            log.info("ATAQUE detectado: cuenta={} ip={} regla={} solicitudes={} deteccion={} ms", cuenta, ip, regla, solicitudes,
                String.format("%.1f", duracionNs / 1e6));
        }
    }
}
