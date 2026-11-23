package co.uniandes.taq.respuesta;

import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Consulta de solo lectura del estado de recuperación (Redis y Postgres), para medir S-2 de forma independiente de
 * las métricas internas y para verificar el estado final.
 */
@RestController
@RequestMapping("/respuesta")
@ConditionalOnProperty(name = "taq.role", havingValue = "respuesta")
public class ConsultaRespuestaController {
    private final StatefulRedisConnection<String, String> redis;
    private final String dbUrl, dbUser, dbPass;
    private Connection db;

    public ConsultaRespuestaController(@Value("${taq.redis-url}") String redisUrl, @Value("${taq.db-url}") String dbUrl,
                                       @Value("${taq.db-user}") String dbUser, @Value("${taq.db-pass}") String dbPass) {
        this.redis = RedisClient.create(redisUrl).connect();
        this.dbUrl = dbUrl; this.dbUser = dbUser; this.dbPass = dbPass;
    }

    private Connection conexion() throws Exception {
        if (db == null || db.isClosed()) db = DriverManager.getConnection(dbUrl, dbUser, dbPass);
        return db;
    }

    /** Por cuenta: revocada en Redis, revocada en Postgres y órdenes canceladas en Postgres. */
    @GetMapping("/estado")
    public synchronized Map<String, Object> estado(@RequestParam String cuentas) throws Exception {
        List<String> lista = Arrays.stream(cuentas.split(",")).filter(s -> !s.isBlank()).toList();
        Map<String, Map<String, Object>> salida = new LinkedHashMap<>();
        for (String c : lista) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("revocada_redis", redis.sync().sismember(RespuestaAtaque.REVOCADAS, c));
            m.put("revocada_postgres", false); m.put("ordenes_canceladas", 0);
            salida.put(c, m);
        }
        if (!lista.isEmpty()) {
            try {
                var arr = conexion().createArrayOf("text", lista.toArray());
                try (PreparedStatement ps = conexion().prepareStatement("SELECT cuenta FROM cuenta_revocada WHERE cuenta = ANY(?)")) {
                    ps.setArray(1, arr);
                    try (ResultSet rs = ps.executeQuery()) { while (rs.next()) salida.get(rs.getString(1)).put("revocada_postgres", true); }
                }
                try (PreparedStatement ps = conexion().prepareStatement(
                    "SELECT comprador, count(*) FROM orden_cancelada WHERE comprador = ANY(?) GROUP BY comprador")) {
                    ps.setArray(1, arr);
                    try (ResultSet rs = ps.executeQuery()) { while (rs.next()) salida.get(rs.getString(1)).put("ordenes_canceladas", rs.getInt(2)); }
                }
            } catch (Exception e) { db = null; throw e; }
        }
        return Map.of("ahora_ms", System.currentTimeMillis(), "cuentas", salida);
    }

    /** Totales para la verificación final; "prefijo" separa las cuentas de bots de las legítimas. */
    @GetMapping("/resumen")
    public synchronized Map<String, Object> resumen(@RequestParam(defaultValue = "bot-") String prefijo) throws Exception {
        Map<String, Object> m = new LinkedHashMap<>();
        try {
            m.put("revocadas_redis", redis.sync().scard(RespuestaAtaque.REVOCADAS));
            m.put("marcadas_redis", redis.sync().scard("cuentas_marcadas"));
            String like = prefijo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%";
            try (PreparedStatement ps = conexion().prepareStatement(
                "SELECT count(*) FILTER (WHERE cuenta LIKE ?), count(*) FILTER (WHERE cuenta NOT LIKE ?) FROM cuenta_revocada")) {
                ps.setString(1, like); ps.setString(2, like);
                try (ResultSet rs = ps.executeQuery()) { rs.next(); m.put("revocadas_postgres_bots", rs.getInt(1)); m.put("revocadas_postgres_otras", rs.getInt(2)); }
            }
            try (PreparedStatement ps = conexion().prepareStatement(
                "SELECT count(*) FILTER (WHERE comprador LIKE ?), count(*) FILTER (WHERE comprador NOT LIKE ?) FROM orden_cancelada")) {
                ps.setString(1, like); ps.setString(2, like);
                try (ResultSet rs = ps.executeQuery()) { rs.next(); m.put("ordenes_canceladas_bots", rs.getInt(1)); m.put("ordenes_canceladas_otras", rs.getInt(2)); }
            }
            try (PreparedStatement ps = conexion().prepareStatement(
                "SELECT count(*) FILTER (WHERE actor_cuenta LIKE ?), count(*) FILTER (WHERE actor_cuenta NOT LIKE ?) "
                + "FROM auditoria_seguridad WHERE tipo = 'ATAQUE_DETECTADO'")) {
                ps.setString(1, like); ps.setString(2, like);
                try (ResultSet rs = ps.executeQuery()) { rs.next(); m.put("marcas_bots", rs.getInt(1)); m.put("marcas_otras", rs.getInt(2)); }
            }
        } catch (Exception e) { db = null; throw e; }
        return m;
    }
}
