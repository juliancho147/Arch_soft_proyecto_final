package co.uniandes.taq.reserva;

import co.uniandes.taq.comun.Json;
import co.uniandes.taq.comun.Metricas;
import io.lettuce.core.KeyValue;
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.annotation.PostConstruct;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * nodo_reserva: componente_receptor_solicitud + componente_gestor_bloqueo + componente_consultor_asiento
 * + componente_confirmador_compra. Los consumidores sacan de cola_solicitud y responden en cola_respuesta.
 */
@RestController
@RequestMapping("/interno")
@ConditionalOnProperty(name = "taq.role", havingValue = "reserva")
public class NodoReserva {
    private final MeterRegistry registro;
    private final RedisClient cliente;
    private final StatefulRedisConnection<String, String> conexion;
    private final HttpClient http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(Duration.ofSeconds(2)).build();
    private final String bloqueoUrl, pasarelaUrl, dbUrl, dbUser, dbPass;
    private final int workers;
    private final Counter cacheHit, cacheMiss;

    public NodoReserva(MeterRegistry registro,
                       @Value("${taq.redis-url}") String redisUrl,
                       @Value("${taq.bloqueo-url}") String bloqueoUrl,
                       @Value("${taq.pasarela-url}") String pasarelaUrl,
                       @Value("${taq.db-url}") String dbUrl, @Value("${taq.db-user}") String dbUser,
                       @Value("${taq.db-pass}") String dbPass, @Value("${taq.workers}") int workers) {
        this.registro = registro;
        this.cliente = RedisClient.create(redisUrl);
        this.conexion = cliente.connect();
        this.bloqueoUrl = bloqueoUrl; this.pasarelaUrl = pasarelaUrl;
        this.dbUrl = dbUrl; this.dbUser = dbUser; this.dbPass = dbPass; this.workers = workers;
        this.cacheHit = Counter.builder("taq_cache_asiento_total").tag("resultado", "hit").register(registro);
        this.cacheMiss = Counter.builder("taq_cache_asiento_total").tag("resultado", "miss").register(registro);
        registro.gauge("taq_cola_persistencia_profundidad", conexion, c -> {
            try { return c.sync().llen("cola_persistencia"); } catch (Exception e) { return -1; }
        });
    }

    @PostConstruct
    void iniciar() throws Exception {
        precalentarCache();
        for (int i = 0; i < workers; i++) {
            Thread t = new Thread(this::consumir, "reserva-worker-" + i);
            t.setDaemon(true); t.start();
        }
        Thread p = new Thread(this::persistir, "persistencia");
        p.setDaemon(true); p.start();
    }

    /** cache_asiento: se precargan 4 de cada 5 asientos; el resto entra por miss y consulta bd_reserva. */
    private void precalentarCache() {
        try {
            var s = conexion.sync();
            if (s.setnx("cache:listo", "1")) {
                var as = conexion.async();
                conexion.setAutoFlushCommands(false);
                for (int id = 1; id <= 130000; id++) {
                    if (id % 5 == 0) continue;
                    as.set("asiento:" + id, "Z" + (id % 4) + "|" + (50000 + (id % 7) * 10000));
                    if (id % 2000 == 0) conexion.flushCommands();
                }
                conexion.flushCommands();
                conexion.setAutoFlushCommands(true);
            }
        } catch (Exception e) {
            conexion.setAutoFlushCommands(true);
        }
    }

    // ---------- Flujo de reservar ----------
    private void consumir() {
        StatefulRedisConnection<String, String> c = cliente.connect();
        try (Connection db = DriverManager.getConnection(dbUrl, dbUser, dbPass)) {
            while (true) {
                try {
                    KeyValue<String, String> kv = c.sync().brpop(1, "cola_solicitud");
                    if (kv == null || !kv.hasValue()) continue;
                    procesar(kv.getValue(), db);
                } catch (Exception e) {
                    try { Thread.sleep(100); } catch (InterruptedException ie) { return; }
                }
            }
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    @SuppressWarnings("unchecked")
    private void procesar(String crudo, Connection db) throws Exception {
        long t0 = System.nanoTime();
        Map<String, Object> m = Json.mapa(crudo);
        String id = (String) m.get("id");
        String gw = (String) m.get("gw");
        List<Integer> asientos = ((List<Number>) m.get("asientos")).stream().map(Number::intValue).toList();
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("id", id);
        resp.put("gw", gw);
        // componente_receptor_solicitud: validación
        if (asientos.isEmpty() || asientos.size() > 4) {
            resp.put("resultado", "SOLICITUD_INVALIDA");
        } else {
            // componente_gestor_bloqueo: única vía hacia bd_bloqueo
            Map<String, Object> r = post(bloqueoUrl + "/bloqueo/bloquear", Json.a(Map.of(
                "solicitudId", id, "comprador", m.get("comprador"), "asientos", asientos)));
            resp.putAll(r);
            if ("OK".equals(r.get("resultado"))) {
                // componente_consultor_asiento: cache_asiento, con bd_reserva si hay miss
                List<String> detalle = new ArrayList<>();
                for (int a : asientos) detalle.add(consultar(a, db));
                resp.put("detalle", detalle);
                // persistencia definitiva asíncrona por cola
                conexion.sync().lpush("cola_persistencia", Json.a(Map.of("asientos", asientos,
                    "comprador", m.get("comprador"), "solicitudId", id, "estado", "BLOQUEADO",
                    "ts", r.get("bloqueadoEn"))));
            }
        }
        conexion.sync().lpush("cola_respuesta:" + gw, Json.a(resp));
        Metricas.timer(registro, "taq_nodo_reserva_proceso_seconds")
            .record(System.nanoTime() - t0, TimeUnit.NANOSECONDS);
    }

    private String consultar(int asiento, Connection db) throws Exception {
        String v = conexion.sync().get("asiento:" + asiento);
        if (v != null) { cacheHit.increment(); return v; }
        cacheMiss.increment();
        try (PreparedStatement ps = db.prepareStatement("SELECT zona, precio FROM asiento WHERE id = ?")) {
            ps.setInt(1, asiento);
            try (ResultSet rs = ps.executeQuery()) {
                v = rs.next() ? rs.getString(1) + "|" + rs.getInt(2) : "?";
            }
        }
        conexion.sync().set("asiento:" + asiento, v);
        return v;
    }

    @SuppressWarnings("unchecked")
    private void persistir() {
        StatefulRedisConnection<String, String> c = cliente.connect();
        try (Connection db = DriverManager.getConnection(dbUrl, dbUser, dbPass);
             PreparedStatement ps = db.prepareStatement(
                 "INSERT INTO reserva_log(asiento, comprador, solicitud_id, estado, ts) VALUES (?,?,?,?,?)")) {
            while (true) {
                try {
                    KeyValue<String, String> kv = c.sync().brpop(1, "cola_persistencia");
                    if (kv == null || !kv.hasValue()) continue;
                    Map<String, Object> m = Json.mapa(kv.getValue());
                    for (Number a : (List<Number>) m.get("asientos")) {
                        ps.setInt(1, a.intValue());
                        ps.setString(2, (String) m.get("comprador"));
                        ps.setString(3, (String) m.get("solicitudId"));
                        ps.setString(4, (String) m.get("estado"));
                        ps.setLong(5, ((Number) m.get("ts")).longValue());
                        ps.addBatch();
                    }
                    ps.executeBatch();
                } catch (Exception e) {
                    try { Thread.sleep(200); } catch (InterruptedException ie) { return; }
                }
            }
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    // ---------- Flujo de confirmar compra: componente_confirmador_compra ----------
    @SuppressWarnings("unchecked")
    @PostMapping(value = "/confirmar", consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> confirmar(@RequestBody Map<String, Object> c) throws Exception {
        String id = (String) c.get("solicitudId");
        Map<String, Object> pago = post(pasarelaUrl + "/pagar", Json.a(Map.of("solicitudId", id)));
        if (!"OK".equals(pago.get("resultado"))) return Map.of("resultado", "PAGO_RECHAZADO");
        Map<String, Object> venta = post(bloqueoUrl + "/bloqueo/vender", Json.a(c));
        if ("OK".equals(venta.get("resultado"))) {
            conexion.sync().lpush("cola_persistencia", Json.a(Map.of("asientos", c.get("asientos"),
                "comprador", c.get("comprador"), "solicitudId", id, "estado", "VENDIDO", "ts", venta.get("vendidoEn"))));
        }
        return venta;
    }

    private Map<String, Object> post(String url, String cuerpo) throws Exception {
        HttpResponse<String> r = http.send(HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(10))
            .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(cuerpo)).build(),
            HttpResponse.BodyHandlers.ofString());
        return Json.mapa(r.body());
    }
}
