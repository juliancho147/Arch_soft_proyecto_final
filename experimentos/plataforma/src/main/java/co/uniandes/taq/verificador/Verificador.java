package co.uniandes.taq.verificador;

import co.uniandes.taq.comun.Json;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Verificador de EXP-1. Cruza (1) la bitácora de lo que envió el generador, (2) la auditoría y el estado final
 * de bd_bloqueo (consultados a través de su cola de operaciones, sin saltarse el hilo único) y
 * (3) el esquema_reserva en PostgreSQL. Escribe verificacion.md y verificacion.json.
 *
 * Uso: Verificador <bitacora.csv> <dirSalida> <bloqueoUrl> <jdbcUrl> <ttlSeg>
 */
public class Verificador {
    record Fila(String solicitud, String tipo, String grupo, String comprador, List<Integer> asientos,
                long ini, long fin, int http, String resultado, String motivo, Long bloqueadoEn, String esperado) {}

    @SuppressWarnings("unchecked")
    public static void main(String[] a) throws Exception {
        Path bit = Path.of(a[0]);
        Path salida = Path.of(a[1]);
        String bloqueoUrl = a[2];
        String jdbc = a[3];
        long ttlMs = Long.parseLong(a[4]) * 1000;

        // ---- 1) bitácora
        List<Fila> filas = new ArrayList<>();
        for (String l : Files.readAllLines(bit).subList(1, (int) Files.lines(bit).count())) {
            String[] c = l.split(",", -1);
            List<Integer> as = Arrays.stream(c[4].split("-")).map(Integer::parseInt).toList();
            filas.add(new Fila(c[0], c[1], c[2], c[3], as, Long.parseLong(c[5]), Long.parseLong(c[6]),
                Integer.parseInt(c[7]), c[8], c[9], c[10].isEmpty() ? null : Long.parseLong(c[10]), c[11]));
        }

        // ---- 2) bd_bloqueo: auditoría y estado final (por su cola de operaciones)
        HttpClient http = HttpClient.newHttpClient();
        List<Map<String, Object>> auditoria = Json.M.readValue(
            http.send(HttpRequest.newBuilder(URI.create(bloqueoUrl + "/bloqueo/auditoria")).build(),
                HttpResponse.BodyHandlers.ofString()).body(), List.class);
        Map<String, Object> estado = Json.mapa(
            http.send(HttpRequest.newBuilder(URI.create(bloqueoUrl + "/bloqueo/estado")).build(),
                HttpResponse.BodyHandlers.ofString()).body());

        // ---- 3) esquema_reserva
        int vendidosDuplicadosBD = 0, bloqueadosDuplicadosBD = 0, filasBD = 0, vendidosBD = 0;
        try (Connection db = DriverManager.getConnection(jdbc, "taq", "taq"); Statement st = db.createStatement()) {
            try (ResultSet rs = st.executeQuery("SELECT count(*) FROM reserva_log")) { rs.next(); filasBD = rs.getInt(1); }
            try (ResultSet rs = st.executeQuery("SELECT count(*) FROM reserva_log WHERE estado='VENDIDO'")) { rs.next(); vendidosBD = rs.getInt(1); }
            try (ResultSet rs = st.executeQuery(
                "SELECT count(*) FROM (SELECT asiento FROM reserva_log WHERE estado='VENDIDO' GROUP BY asiento HAVING count(*)>1) x")) {
                rs.next(); vendidosDuplicadosBD = rs.getInt(1); }
            // dos BLOQUEADO del mismo asiento con menos de ttl de diferencia = doble reserva
            try (ResultSet rs = st.executeQuery(
                "SELECT count(DISTINCT a.asiento) FROM reserva_log a JOIN reserva_log b ON a.asiento=b.asiento AND a.id<b.id " +
                "WHERE a.estado='BLOQUEADO' AND b.estado='BLOQUEADO' AND abs(b.ts-a.ts) < " + ttlMs)) {
                rs.next(); bloqueadosDuplicadosBD = rs.getInt(1); }
        }

        // ---- D-3 (a): doble reserva según la auditoría de bd_bloqueo, reproduciendo la secuencia por asiento
        Map<Integer, List<Map<String, Object>>> porAsiento = new TreeMap<>();
        for (Map<String, Object> e : auditoria) porAsiento.computeIfAbsent(((Number) e.get("asiento")).intValue(), k -> new ArrayList<>()).add(e);
        Set<Integer> asientosDoble = new TreeSet<>();
        for (var en : porAsiento.entrySet()) {
            boolean ocupado = false;
            for (Map<String, Object> e : en.getValue()) {      // la auditoría ya está en el orden del hilo único
                String t = (String) e.get("tipo");
                if (t.equals("BLOQUEO")) { if (ocupado) asientosDoble.add(en.getKey()); ocupado = true; }
                else ocupado = false;                           // VENTA y LIBERACION cierran el bloqueo
            }
        }

        // ---- D-3 (b): doble reserva según la bitácora del cliente (intervalos de bloqueo solapados)
        Map<Integer, List<Fila>> okPorAsiento = new TreeMap<>();
        for (Fila f : filas) if (f.resultado.equals("OK") && !f.tipo.equals("CONFIRMAR"))
            for (int s : f.asientos) okPorAsiento.computeIfAbsent(s, k -> new ArrayList<>()).add(f);
        Set<Integer> dobleBitacora = new TreeSet<>();
        Set<String> confirmadasOk = filas.stream().filter(f -> f.tipo.equals("CONFIRMAR") && f.resultado.equals("OK"))
            .map(Fila::solicitud).collect(Collectors.toSet());
        for (var en : okPorAsiento.entrySet()) {
            List<Fila> l = new ArrayList<>(en.getValue());
            l.sort(Comparator.comparingLong(f -> f.bloqueadoEn));
            for (int i = 1; i < l.size(); i++) {
                Fila prev = l.get(i - 1), cur = l.get(i);
                if (confirmadasOk.contains(prev.solicitud) || cur.bloqueadoEn < prev.bloqueadoEn + ttlMs) dobleBitacora.add(en.getKey());
            }
        }

        // ---- D-3: todo o nada
        Map<String, Set<Integer>> bloqueosPorSolicitud = new HashMap<>();
        for (Map<String, Object> e : auditoria) if (e.get("tipo").equals("BLOQUEO"))
            bloqueosPorSolicitud.computeIfAbsent((String) e.get("solicitudId"), k -> new TreeSet<>()).add(((Number) e.get("asiento")).intValue());
        int parciales = 0, gruposMultiples = 0, rechazadosMultiplesLimpios = 0;
        for (Fila f : filas) {
            if (f.tipo.equals("CONFIRMAR")) continue;
            Set<Integer> bl = bloqueosPorSolicitud.getOrDefault(f.solicitud, Set.of());
            boolean ok = f.resultado.equals("OK");
            if (f.asientos.size() > 1) gruposMultiples++;
            if (ok ? !bl.equals(new TreeSet<>(f.asientos)) : !bl.isEmpty()) parciales++;
            else if (!ok && f.asientos.size() > 1 && f.resultado.equals("NO_DISPONIBLE")) rechazadosMultiplesLimpios++;
        }
        // Bloqueos que existen en bd_bloqueo pero cuyo cliente no recibió OK
        Set<String> solicitudesOk = filas.stream().filter(f -> f.resultado.equals("OK") && !f.tipo.equals("CONFIRMAR")).map(Fila::solicitud).collect(Collectors.toSet());
        int huerfanos = (int) bloqueosPorSolicitud.keySet().stream().filter(s -> !solicitudesOk.contains(s)).count();

        // ---- Conflictos
        Map<String, List<Fila>> grupos = filas.stream().filter(f -> !f.grupo.isEmpty()).collect(Collectors.groupingBy(Fila::grupo));
        Map<String, int[]> resumenTipo = new TreeMap<>();   // tipo -> {conflictos, cumplen, solicitudes}
        int conflictosFallidos = 0;
        List<String> detalleFallos = new ArrayList<>();
        for (var g : grupos.entrySet()) {
            List<Fila> l = g.getValue();
            String tipo = l.get(0).tipo.startsWith("CONF_MISMO_ASIENTO") ? "CONF_MISMO_ASIENTO" : l.get(0).tipo;
            boolean cumple;
            if (tipo.equals("CONF_MISMO_ASIENTO")) cumple = l.stream().filter(f -> f.resultado.equals("OK")).count() == 1;
            else if (tipo.equals("CONF_VENDIDO")) cumple = l.stream().allMatch(f -> f.resultado.equals("NO_DISPONIBLE") && f.motivo.equals("VENDIDO"));
            else { // grupos cruzados: algún ganador y cada asiento con a lo sumo un ganador
                Map<Integer, Integer> cuenta = new HashMap<>();
                for (Fila f : l) if (f.resultado.equals("OK")) for (int s : f.asientos) cuenta.merge(s, 1, Integer::sum);
                cumple = !cuenta.isEmpty() && cuenta.values().stream().allMatch(v -> v == 1);
            }
            int[] r = resumenTipo.computeIfAbsent(tipo, k -> new int[3]);
            r[0]++; r[2] += l.size(); if (cumple) r[1]++; else { conflictosFallidos++; detalleFallos.add(g.getKey() + " (" + tipo + ")"); }
        }

        // ---- Revisiones de abandono
        long r4 = filas.stream().filter(f -> f.tipo.equals("REVISION_4MIN")).count();
        long r4ok = filas.stream().filter(f -> f.tipo.equals("REVISION_4MIN") && f.resultado.equals("NO_DISPONIBLE")).count();
        long r8 = filas.stream().filter(f -> f.tipo.equals("REVISION_8MIN")).count();
        long r8ok = filas.stream().filter(f -> f.tipo.equals("REVISION_8MIN") && f.resultado.equals("OK")).count();

        // ---- Liberación real del bloqueo (de auditoría: BLOQUEO -> LIBERACION del mismo asiento y solicitud)
        List<Double> liberaciones = new ArrayList<>();
        for (var en : porAsiento.entrySet()) {
            Map<String, Long> abiertos = new HashMap<>();
            for (Map<String, Object> e : en.getValue()) {
                String sol = (String) e.get("solicitudId"); long ts = ((Number) e.get("ts")).longValue();
                if (e.get("tipo").equals("BLOQUEO")) abiertos.put(sol, ts);
                else if (e.get("tipo").equals("LIBERACION") && abiertos.containsKey(sol)) liberaciones.add((ts - abiertos.get(sol)) / 1000.0);
            }
        }
        Collections.sort(liberaciones);

        // ---- Llegadas normales
        long normales = filas.stream().filter(f -> f.tipo.equals("NORMAL")).count();
        long normalesOk = filas.stream().filter(f -> f.tipo.equals("NORMAL") && f.resultado.equals("OK")).count();
        long confirmaciones = filas.stream().filter(f -> f.tipo.equals("CONFIRMAR")).count();
        long confirmacionesOk = filas.stream().filter(f -> f.tipo.equals("CONFIRMAR") && f.resultado.equals("OK")).count();
        long reservasTotales = filas.stream().filter(f -> !f.tipo.equals("CONFIRMAR")).count();
        long erroresTecnicos = filas.stream().filter(f -> f.http >= 500 || f.http == 0 || f.resultado.startsWith("ERROR") || f.resultado.equals("TIMEOUT") || f.resultado.equals("COLA_LLENA")).count();
        int vendidosEstado = ((Map<String, Object>) estado.get("vendidos")).size();
        int bloqueadosFinal = ((List<?>) estado.get("bloqueados")).size();

        Map<String, Object> j = new LinkedHashMap<>();
        j.put("asientos_con_mas_de_una_reserva_auditoria", asientosDoble.size());
        j.put("asientos_con_mas_de_una_reserva_bitacora", dobleBitacora.size());
        j.put("asientos_vendidos_duplicados_bd_reserva", vendidosDuplicadosBD);
        j.put("asientos_bloqueados_duplicados_bd_reserva", bloqueadosDuplicadosBD);
        j.put("bloqueos_parciales", parciales);
        j.put("bloqueos_huerfanos_sin_ok_en_cliente", huerfanos);
        j.put("conflictos_total", grupos.size());
        j.put("conflictos_con_resultado_esperado", grupos.size() - conflictosFallidos);
        j.put("conflictos_fallidos", detalleFallos);
        j.put("revisiones_4min_total", r4); j.put("revisiones_4min_rechazadas", r4ok);
        j.put("revisiones_8min_total", r8); j.put("revisiones_8min_exitosas", r8ok);
        j.put("liberaciones_total", liberaciones.size());
        j.put("liberacion_min_s", liberaciones.isEmpty() ? null : liberaciones.get(0));
        j.put("liberacion_p50_s", liberaciones.isEmpty() ? null : liberaciones.get(liberaciones.size() / 2));
        j.put("liberacion_max_s", liberaciones.isEmpty() ? null : liberaciones.get(liberaciones.size() - 1));
        j.put("llegadas_normales", normales); j.put("llegadas_normales_ok", normalesOk);
        j.put("confirmaciones", confirmaciones); j.put("confirmaciones_ok", confirmacionesOk);
        j.put("solicitudes_reservar_total", reservasTotales);
        j.put("errores_tecnicos", erroresTecnicos);
        j.put("filas_reserva_log", filasBD); j.put("vendidos_reserva_log", vendidosBD);
        j.put("vendidos_estado_bd_bloqueo", vendidosEstado);
        j.put("bloqueos_activos_al_final", bloqueadosFinal);
        Map<String, Object> tipos = new LinkedHashMap<>();
        resumenTipo.forEach((k, v) -> tipos.put(k, Map.of("conflictos", v[0], "con_resultado_esperado", v[1], "solicitudes", v[2])));
        j.put("conflictos_por_tipo", tipos);
        Files.createDirectories(salida);
        Files.writeString(salida.resolve("verificacion.json"), Json.M.writerWithDefaultPrettyPrinter().writeValueAsString(j));

        boolean d3 = asientosDoble.isEmpty() && dobleBitacora.isEmpty() && vendidosDuplicadosBD == 0 && bloqueadosDuplicadosBD == 0
            && parciales == 0 && huerfanos == 0 && conflictosFallidos == 0 && vendidosBD == vendidosEstado;
        StringBuilder md = new StringBuilder();
        md.append("# Verificación D-3 — ").append(salida.getFileName()).append("\n\n");
        md.append("**Veredicto D-3: ").append(d3 ? "CUMPLE ✅" : "NO CUMPLE ❌").append("**\n\n");
        md.append("| Comprobación | Esperado | Obtenido |\n|---|---|---|\n");
        md.append(fila("Asientos con más de una reserva (auditoría de `bd_bloqueo`)", "0", asientosDoble.size()));
        md.append(fila("Asientos con más de una reserva (bitácora del cliente)", "0", dobleBitacora.size()));
        md.append(fila("Asientos vendidos más de una vez (`reserva_log`)", "0", vendidosDuplicadosBD));
        md.append(fila("Asientos bloqueados dos veces dentro del TTL (`reserva_log`)", "0", bloqueadosDuplicadosBD));
        md.append(fila("Bloqueos parciales (todo o nada roto)", "0", parciales));
        md.append(fila("Bloqueos sin OK en el cliente", "0", huerfanos));
        md.append(fila("Conflictos con el resultado esperado", grupos.size() + " de " + grupos.size(), (grupos.size() - conflictosFallidos) + " de " + grupos.size()));
        md.append(fila("Vendidos en `reserva_log` = vendidos en `bd_bloqueo`", "iguales", vendidosBD + " = " + vendidosEstado));
        md.append("\n## Conflictos por tipo\n\n| Tipo | Conflictos | Con resultado esperado | Solicitudes |\n|---|---|---|---|\n");
        resumenTipo.forEach((k, v) -> md.append("| ").append(k).append(" | ").append(v[0]).append(" | ").append(v[1]).append(" | ").append(v[2]).append(" |\n"));
        md.append("\n## Vencimiento de bloqueos abandonados\n\n| Comprobación | Esperado | Obtenido |\n|---|---|---|\n");
        md.append(fila("Revisión a los 4 min rechazada", "todas", r4ok + " de " + r4));
        md.append(fila("Revisión pasados los 8 min exitosa", "todas", r8ok + " de " + r8));
        md.append(fila("Bloqueos liberados por vencimiento", "—", liberaciones.size()));
        if (!liberaciones.isEmpty())
            md.append(fila("Tiempo real bloqueo→liberación (mín / p50 / máx, s)", "≈ 480", String.format(Locale.ROOT, "%.2f / %.2f / %.2f", liberaciones.get(0), liberaciones.get(liberaciones.size() / 2), liberaciones.get(liberaciones.size() - 1))));
        md.append("\n## Volumen de la corrida\n\n| Dato | Valor |\n|---|---|\n");
        md.append("| Solicitudes de reservar (normales + conflictos + revisiones) | ").append(reservasTotales).append(" |\n");
        md.append("| Llegadas normales / con éxito | ").append(normales).append(" / ").append(normalesOk).append(" |\n");
        md.append("| Confirmaciones / con éxito | ").append(confirmaciones).append(" / ").append(confirmacionesOk).append(" |\n");
        md.append("| Errores técnicos (5xx, timeouts, cola llena) | ").append(erroresTecnicos).append(" |\n");
        md.append("| Asientos vendidos | ").append(vendidosEstado).append(" |\n");
        md.append("| Bloqueos activos al terminar | ").append(bloqueadosFinal).append(" |\n");
        if (!detalleFallos.isEmpty()) md.append("\n## Conflictos fallidos\n\n").append(String.join(", ", detalleFallos)).append("\n");
        Files.writeString(salida.resolve("verificacion.md"), md.toString());
        System.out.println(md);
        System.exit(d3 ? 0 : 2);
    }

    private static String fila(String c, Object esp, Object obt) {
        return "| " + c + " | " + esp + " | " + obt + " |\n";
    }
}
