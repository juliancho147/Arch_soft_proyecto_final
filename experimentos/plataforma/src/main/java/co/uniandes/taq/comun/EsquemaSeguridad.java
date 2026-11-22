package co.uniandes.taq.comun;

import java.sql.Connection;
import java.sql.Statement;

/** EXP-3: tablas de seguridad (bd_auditoria y estado de recuperación). Se crean al arrancar, sin tocar reserva_log. */
public final class EsquemaSeguridad {
    private EsquemaSeguridad() {}

    public static void crear(Connection db) throws Exception {
        try (Statement st = db.createStatement()) {
            // bd_auditoria: evidencia de detección (IP, cuenta, horarios) y de recuperación.
            st.execute("CREATE TABLE IF NOT EXISTS auditoria_seguridad (id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT now(), "
                + "tipo TEXT NOT NULL, actor_cuenta TEXT, actor_ip TEXT, detalle JSONB, "
                + "ts_evento_detector BIGINT, ts_evidencia BIGINT)");
            st.execute("CREATE INDEX IF NOT EXISTS auditoria_seguridad_tipo ON auditoria_seguridad(tipo, id)");
            st.execute("CREATE TABLE IF NOT EXISTS cuenta_revocada (cuenta TEXT PRIMARY KEY, ts_ms BIGINT NOT NULL, motivo TEXT, alerta_id TEXT)");
            // Cancelación de órdenes: reserva_log es un registro de solo anexar (sin unicidad ni índice por comprador);
            // la cancelación se anota aparte, una fila por solicitud (orden) retenida que se liberó.
            st.execute("CREATE TABLE IF NOT EXISTS orden_cancelada (solicitud_id TEXT PRIMARY KEY, comprador TEXT NOT NULL, "
                + "asientos TEXT NOT NULL, ts_ms BIGINT NOT NULL, motivo TEXT)");
            st.execute("CREATE INDEX IF NOT EXISTS orden_cancelada_comprador ON orden_cancelada(comprador)");
        }
    }
}
