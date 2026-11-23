package co.uniandes.taq.gateway;

import co.uniandes.taq.comun.Json;
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.annotation.PostConstruct;
import jakarta.servlet.http.HttpServletRequest;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.stereotype.Component;

/**
 * EXP-3, lado del gateway (solo con TAQ_DETECCION=on): publica cada solicitud como evento en cola_evento_trafico SIN esperar
 * (comando asíncrono de Lettuce, acotado) y rechaza las cuentas revocadas consultando una copia local en memoria del
 * conjunto Redis cuentas_revocadas, refrescada cada ~1 s (cero costo de red por solicitud).
 */
@Component
@ConditionalOnExpression("'${taq.role}'=='gateway' and '${taq.deteccion:off}'=='on'")
public class EventosTrafico {
    private static final Logger log = LoggerFactory.getLogger(EventosTrafico.class);
    public static final String COLA = "cola_evento_trafico", REVOCADAS = "cuentas_revocadas";

    private final StatefulRedisConnection<String, String> escritura, lectura;
    private final long colaMax, refrescoMs;
    private final int vueloMax;
    private final AtomicInteger enVuelo = new AtomicInteger();
    private volatile long profundidad = 0;
    private volatile Set<String> revocadas = Set.of();
    private final Counter publicados, descartados, rechazosRevocada;

    public EventosTrafico(MeterRegistry registro, @Value("${taq.redis-url}") String redisUrl,
                          @Value("${taq.evento-cola-max}") long colaMax, @Value("${taq.evento-vuelo-max}") int vueloMax,
                          @Value("${taq.revocadas-refresco-ms}") long refrescoMs) {
        RedisClient c = RedisClient.create(redisUrl);
        this.escritura = c.connect();
        this.lectura = c.connect();
        this.colaMax = colaMax; this.vueloMax = vueloMax; this.refrescoMs = refrescoMs;
        this.publicados = Counter.builder("taq_eventos_trafico_publicados_total").register(registro);
        this.descartados = Counter.builder("taq_eventos_trafico_descartados_total").register(registro);
        this.rechazosRevocada = Counter.builder("taq_rechazos_cuenta_revocada_total").register(registro);
        registro.gauge("taq_eventos_en_vuelo", enVuelo, AtomicInteger::get);
    }

    @PostConstruct
    void iniciar() {
        Thread t = new Thread(() -> {
            long ultimaProfundidad = 0;
            while (true) {
                try {
                    revocadas = Set.copyOf(lectura.sync().smembers(REVOCADAS));
                    long ahora = System.currentTimeMillis();
                    if (ahora - ultimaProfundidad >= 1000) { profundidad = lectura.sync().llen(COLA); ultimaProfundidad = ahora; }
                } catch (Exception e) {
                    log.warn("No se pudo refrescar cuentas revocadas / profundidad: {}", e.toString());
                }
                try { Thread.sleep(refrescoMs); } catch (InterruptedException ie) { return; }
            }
        }, "gw-eventos-refresco");
        t.setDaemon(true);
        t.start();
    }

    public boolean estaRevocada(String cuenta) { return revocadas.contains(cuenta); }

    public void contarRechazo() { rechazosRevocada.increment(); }

    /** IP simulada: primer valor de X-Forwarded-For; si falta, la IP remota (en ese caso la regla por IP no se aplica). */
    public static String[] ip(HttpServletRequest req) {
        String xff = req.getHeader("X-Forwarded-For");
        if (xff != null && !xff.isBlank()) return new String[] {xff.split(",")[0].trim(), "xff"};
        return new String[] {req.getRemoteAddr(), "remota"};
    }

    /** Fire-and-forget: no bloquea la solicitud del comprador ni propaga errores de Redis. */
    public void publicar(String ruta, HttpServletRequest req, String cuenta, Object asientos, String solicitudId) {
        publicar(ruta, req, cuenta, asientos, solicitudId, null);
    }

    /** tipoAtacante: etiqueta que el generador del experimento declara en la solicitud (null si no viene; el tráfico legítimo no la lleva). */
    public void publicar(String ruta, HttpServletRequest req, String cuenta, Object asientos, String solicitudId, Object tipoAtacante) {
        if (profundidad >= colaMax || enVuelo.get() >= vueloMax) { descartados.increment(); return; }
        try {
            String[] ip = ip(req);
            Map<String, Object> e = new LinkedHashMap<>();
            e.put("ts_ms", System.currentTimeMillis()); e.put("ip", ip[0]); e.put("ip_fuente", ip[1]);
            e.put("cuenta", cuenta); e.put("ruta", ruta); e.put("asientos", asientos); e.put("solicitudId", solicitudId);
            if (tipoAtacante != null) e.put("tipo_atacante", String.valueOf(tipoAtacante));
            enVuelo.incrementAndGet();
            escritura.async().lpush(COLA, Json.a(e)).whenComplete((r, ex) -> enVuelo.decrementAndGet());
            publicados.increment();
        } catch (Exception ex) {
            descartados.increment();
        }
    }
}
