package co.uniandes.taq.deteccion;

import co.uniandes.taq.comun.Json;
import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import jakarta.annotation.PostConstruct;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * componente_parametrizacion: reglas antifraude en el hash Redis "parametros_antifraude".
 * El detector las relee cada ~5 s; los cambios por la API se aplican de inmediato en esta réplica.
 */
@Component
@ConditionalOnProperty(name = "taq.role", havingValue = "deteccion")
public class Parametros {
    public static final String HASH = "parametros_antifraude";
    private static final Logger log = LoggerFactory.getLogger(Parametros.class);

    /** Reglas inmutables: se reemplazan completas para que el detector lea un conjunto coherente. */
    public record Reglas(int ventanaS, int umbralCuenta, int umbralIp, int umbralAsientos) {
        Map<String, Object> mapa() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("ventana_s", ventanaS); m.put("umbral_cuenta", umbralCuenta);
            m.put("umbral_ip", umbralIp); m.put("umbral_asientos", umbralAsientos);
            return m;
        }
    }

    private final StatefulRedisConnection<String, String> redis;
    private volatile Reglas reglas;

    public Parametros(@Value("${taq.redis-url}") String redisUrl,
                      @Value("${taq.antifraude.ventana-s}") int ventanaS,
                      @Value("${taq.antifraude.umbral-cuenta}") int umbralCuenta,
                      @Value("${taq.antifraude.umbral-ip}") int umbralIp,
                      @Value("${taq.antifraude.umbral-asientos}") int umbralAsientos) {
        this.redis = RedisClient.create(redisUrl).connect();
        this.reglas = new Reglas(ventanaS, umbralCuenta, umbralIp, umbralAsientos);
    }

    @PostConstruct
    void iniciar() {
        try {   // siembra los valores por defecto sin pisar lo que ya haya definido el operador
            for (var e : reglas.mapa().entrySet()) redis.sync().hsetnx(HASH, e.getKey(), String.valueOf(e.getValue()));
        } catch (Exception e) { log.warn("No se pudieron sembrar los parámetros en Redis: {}", e.toString()); }
        refrescar();
        Thread t = new Thread(() -> {
            while (true) {
                try { Thread.sleep(5000); } catch (InterruptedException ie) { return; }
                refrescar();
            }
        }, "parametros-refresco");
        t.setDaemon(true);
        t.start();
    }

    public Reglas reglas() { return reglas; }

    private void refrescar() {
        try {
            Map<String, String> h = redis.sync().hgetall(HASH);
            if (h.isEmpty()) return;
            Reglas a = reglas;
            reglas = new Reglas(entero(h, "ventana_s", a.ventanaS()), entero(h, "umbral_cuenta", a.umbralCuenta()),
                entero(h, "umbral_ip", a.umbralIp()), entero(h, "umbral_asientos", a.umbralAsientos()));
        } catch (Exception e) { log.warn("No se pudieron leer los parámetros: {}", e.toString()); }
    }

    private static int entero(Map<String, String> h, String k, int defecto) {
        try { return h.containsKey(k) ? Integer.parseInt(h.get(k).trim()) : defecto; } catch (NumberFormatException e) { return defecto; }
    }

    /** Cambia parámetros (PUT): valida, guarda en Redis y aplica ya en esta réplica. */
    public Map<String, Object> cambiar(Map<String, Object> nuevos) {
        Map<String, String> aEscribir = new LinkedHashMap<>();
        for (String k : reglas.mapa().keySet()) {
            if (!nuevos.containsKey(k)) continue;
            int v = ((Number) nuevos.get(k)).intValue();
            if (v < 0 || (k.equals("ventana_s") && v < 1)) throw new IllegalArgumentException("valor inválido para " + k);
            aEscribir.put(k, String.valueOf(v));
        }
        if (!aEscribir.isEmpty()) redis.sync().hset(HASH, aEscribir);
        refrescar();
        return reglas.mapa();
    }

    public String json() { return Json.a(reglas.mapa()); }
}
