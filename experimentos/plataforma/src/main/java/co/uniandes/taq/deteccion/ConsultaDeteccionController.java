package co.uniandes.taq.deteccion;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Consulta de bd_auditoria (solo lectura) para los scripts de medición y verificación de EXP-3. */
@RestController
@RequestMapping("/deteccion")
@ConditionalOnProperty(name = "taq.role", havingValue = "deteccion")
public class ConsultaDeteccionController {
    private final String dbUrl, dbUser, dbPass;
    private Connection db;

    public ConsultaDeteccionController(@Value("${taq.db-url}") String dbUrl, @Value("${taq.db-user}") String dbUser,
                                       @Value("${taq.db-pass}") String dbPass) {
        this.dbUrl = dbUrl; this.dbUser = dbUser; this.dbPass = dbPass;
    }

    private synchronized Connection conexion() throws Exception {
        if (db == null || db.isClosed()) db = DriverManager.getConnection(dbUrl, dbUser, dbPass);
        return db;
    }

    /** Filas de auditoria_seguridad con id mayor que "desde" (paginadas), en orden de id. */
    @GetMapping("/auditoria")
    public synchronized List<Map<String, Object>> auditoria(@RequestParam(defaultValue = "0") long desde,
                                                            @RequestParam(defaultValue = "1000") int limite,
                                                            @RequestParam(defaultValue = "") String tipo) throws Exception {
        String sql = "SELECT id, tipo, actor_cuenta, actor_ip, detalle::text, ts_evento_detector, ts_evidencia FROM auditoria_seguridad "
            + "WHERE id > ?" + (tipo.isEmpty() ? "" : " AND tipo = ?") + " ORDER BY id LIMIT ?";
        List<Map<String, Object>> filas = new ArrayList<>();
        try (PreparedStatement ps = conexion().prepareStatement(sql)) {
            int i = 1;
            ps.setLong(i++, desde);
            if (!tipo.isEmpty()) ps.setString(i++, tipo);
            ps.setInt(i, Math.min(limite, 20000));
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    Map<String, Object> f = new LinkedHashMap<>();
                    f.put("id", rs.getLong(1)); f.put("tipo", rs.getString(2)); f.put("cuenta", rs.getString(3));
                    f.put("ip", rs.getString(4)); f.put("detalle", rs.getString(5));
                    f.put("ts_evento_detector", rs.getLong(6)); f.put("ts_evidencia", rs.getLong(7));
                    filas.add(f);
                }
            }
        } catch (Exception e) { db = null; throw e; }
        return filas;
    }
}
