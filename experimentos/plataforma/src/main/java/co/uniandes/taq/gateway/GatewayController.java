package co.uniandes.taq.gateway;

import co.uniandes.taq.comun.Json;
import co.uniandes.taq.comun.Metricas;
import io.lettuce.core.KeyValue;
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.annotation.PostConstruct;
import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** componente_api_gateway: publica en cola_solicitud y espera la respuesta de cola_respuesta. */
@RestController
@RequestMapping("/api")
@ConditionalOnProperty(name = "taq.role", havingValue = "gateway")
public class GatewayController {
    private final MeterRegistry registro;
    private final String pod;
    private final String reservaUrl;
    private final int colaMax;
    private final StatefulRedisConnection<String, String> conexion;
    private final RedisClient cliente;
    private final HttpClient http = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(Duration.ofSeconds(2)).build();
    private final Map<String, CompletableFuture<Map<String, Object>>> pendientes = new ConcurrentHashMap<>();
    private final Counter rechazosCola;
    private final EventosTrafico eventos;     // null con TAQ_DETECCION=off (EXP-1 y EXP-2 no cambian)

    public GatewayController(MeterRegistry registro,
                             @Value("${taq.redis-url}") String redisUrl,
                             @Value("${taq.reserva-url}") String reservaUrl,
                             @Value("${taq.cola-max}") int colaMax,
                             @Value("${taq.pod}") String pod,
                             ObjectProvider<EventosTrafico> eventos) {
        this.eventos = eventos.getIfAvailable();
        this.registro = registro;
        this.pod = pod;
        this.reservaUrl = reservaUrl;
        this.colaMax = colaMax;
        this.cliente = RedisClient.create(redisUrl);
        this.conexion = cliente.connect();
        this.rechazosCola = Counter.builder("taq_rechazos_cola_llena_total").register(registro);
        registro.gauge("taq_cola_solicitud_profundidad", conexion, c -> {
            try { return c.sync().llen("cola_solicitud"); } catch (Exception e) { return -1; }
        });
        registro.gauge("taq_cola_respuesta_profundidad", conexion, c -> {
            try { return c.sync().llen("cola_respuesta:" + pod); } catch (Exception e) { return -1; }
        });
    }

    @PostConstruct
    void iniciarEscuchaRespuestas() {
        Thread t = new Thread(() -> {
            StatefulRedisConnection<String, String> c = cliente.connect();
            while (true) {
                try {
                    KeyValue<String, String> kv = c.sync().brpop(1, "cola_respuesta:" + pod);
                    if (kv == null || !kv.hasValue()) continue;
                    Map<String, Object> resp = Json.mapa(kv.getValue());
                    CompletableFuture<Map<String, Object>> f = pendientes.remove((String) resp.get("id"));
                    if (f != null) f.complete(resp);
                } catch (Exception e) {
                    try { Thread.sleep(200); } catch (InterruptedException ie) { return; }
                }
            }
        }, "gw-respuestas");
        t.setDaemon(true);
        t.start();
    }

    @PostMapping(value = "/reservar", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, Object>> reservar(@RequestBody Map<String, Object> cuerpo, HttpServletRequest req) {
        long t0 = System.nanoTime();
        String id = String.valueOf(cuerpo.get("solicitudId"));
        if (eventos != null) {   // EXP-3: cuenta revocada -> 403; si no, el evento se publica sin esperar
            String cuenta = String.valueOf(cuerpo.get("comprador"));
            if (eventos.estaRevocada(cuenta)) {
                eventos.contarRechazo();
                return ResponseEntity.status(403).body(Map.of("resultado", "CUENTA_REVOCADA"));
            }
            eventos.publicar("reservar", req, cuenta, cuerpo.get("asientos"), id, cuerpo.get("tipoAtacante"));
        }
        String resultado = "ERROR";
        int http = 200;
        Map<String, Object> salida = new LinkedHashMap<>();
        try {
            long profundidad = conexion.sync().llen("cola_solicitud");
            if (profundidad >= colaMax) {            // Acotar el tamaño de colas
                rechazosCola.increment();
                resultado = "COLA_LLENA"; http = 429;
                salida.put("resultado", resultado);
                return ResponseEntity.status(http).body(salida);
            }
            CompletableFuture<Map<String, Object>> futuro = new CompletableFuture<>();
            pendientes.put(id, futuro);
            Map<String, Object> msg = new LinkedHashMap<>(cuerpo);
            msg.put("id", id);
            msg.put("gw", pod);
            conexion.sync().lpush("cola_solicitud", Json.a(msg));
            Map<String, Object> resp = futuro.get(5, TimeUnit.SECONDS);
            resultado = String.valueOf(resp.get("resultado"));
            salida.putAll(resp);
            salida.remove("gw");
            return ResponseEntity.ok(salida);
        } catch (java.util.concurrent.TimeoutException e) {
            pendientes.remove(id);
            resultado = "TIMEOUT"; http = 504;
            salida.put("resultado", resultado);
            return ResponseEntity.status(http).body(salida);
        } catch (Exception e) {
            pendientes.remove(id);
            http = 500;
            salida.put("resultado", "ERROR");
            salida.put("detalle", String.valueOf(e));
            return ResponseEntity.status(http).body(salida);
        } finally {
            Metricas.timer(registro, "taq_reservar_seconds", "resultado", resultado)
                .record(System.nanoTime() - t0, TimeUnit.NANOSECONDS);
        }
    }

    @PostMapping(value = "/confirmar", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> confirmar(@RequestBody String cuerpo, HttpServletRequest req) throws Exception {
        long t0 = System.nanoTime();
        if (eventos != null) {   // EXP-3
            Map<String, Object> m = Json.mapa(cuerpo);
            String cuenta = String.valueOf(m.get("comprador"));
            if (eventos.estaRevocada(cuenta)) {
                eventos.contarRechazo();
                return ResponseEntity.status(403).contentType(MediaType.APPLICATION_JSON).body("{\"resultado\":\"CUENTA_REVOCADA\"}");
            }
            eventos.publicar("confirmar", req, cuenta, m.get("asientos"), String.valueOf(m.get("solicitudId")));
        }
        String resultado = "ERROR";
        try {
            HttpResponse<String> r = http.send(HttpRequest.newBuilder(URI.create(reservaUrl + "/interno/confirmar"))
                .timeout(Duration.ofSeconds(10)).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(cuerpo)).build(), HttpResponse.BodyHandlers.ofString());
            resultado = String.valueOf(Json.mapa(r.body()).get("resultado"));
            return ResponseEntity.status(r.statusCode()).contentType(MediaType.APPLICATION_JSON).body(r.body());
        } finally {
            Metricas.timer(registro, "taq_confirmar_seconds", "resultado", resultado)
                .record(System.nanoTime() - t0, TimeUnit.NANOSECONDS);
        }
    }
}
