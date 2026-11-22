package co.uniandes.taq.bloqueo;

import co.uniandes.taq.comun.Metricas;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * proceso_bd_bloqueo: cola_operacion + hilo_unico + estado_asiento + proceso_vencimiento.
 * TODO el estado se toca únicamente desde el hilo único; no hay locks.
 */
@Component
@ConditionalOnProperty(name = "taq.role", havingValue = "bloqueo")
public class BdBloqueo {
    record Bloqueo(String solicitudId, String comprador, long bloqueadoEn, long venceEn, java.util.concurrent.atomic.AtomicBoolean conflicto, java.util.concurrent.atomic.AtomicBoolean contada) {}

    private final Map<Integer, Bloqueo> bloqueados = new HashMap<>();
    private final Map<Integer, String> vendidos = new HashMap<>();   // asiento -> comprador
    private final List<Map<String, Object>> auditoria = new ArrayList<>();

    private final LinkedBlockingQueue<Runnable> colaOperacion = new LinkedBlockingQueue<>();
    private final ThreadPoolExecutor hiloUnico;
    private final ScheduledExecutorService vencimiento = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "proceso-vencimiento"); t.setDaemon(true); return t;
    });
    private final long ttlMs;
    // EXP-3 (solo con TAQ_DETECCION=on; apagado no se toca): índice comprador -> asientos que retiene, SIEMPRE mantenido
    // dentro del hilo único, y compradores revocados cuyas reservas nuevas se rechazan.
    private final boolean indice;
    private final Map<String, Set<Integer>> porComprador = new HashMap<>();
    private final Set<String> revocados = new HashSet<>();
    private final Counter liberadosAtaque;
    private final Timer liberacionAtaque, operacionAtaque;
    private final AtomicLong ocupadoNanos = new AtomicLong();
    private final Timer liberacion;
    private final Timer esperaCola;
    // Visibilidad de conflictos: solicitudes a una misma silla en una ventana corta (solo se lee/escribe en el hilo único).
    private static final long VENTANA_CONFLICTO_MS = 2000, RETENCION_PICO_MS = 12000;
    private final Map<Integer, java.util.ArrayDeque<Long>> llegadas = new HashMap<>();
    private volatile int picoMismaSilla = 0;
    private volatile long picoEn = 0;
    // Última ráfaga de conflicto (valores exactos, retenidos 12 s para que Prometheus los alcance a muestrear).
    private volatile int rafagaAprobadas = 0, rafagaCanceladas = 0;
    private volatile long rafagaUlt = 0;
    private final Counter conflictoConfirmada, conflictoCancelada;
    private final Counter opsBloquear, opsVender, liberadosPorVencimiento;
    private final MeterRegistry registro;

    public BdBloqueo(MeterRegistry registro, @Value("${taq.ttl-seg}") long ttlSeg,
                     @Value("${taq.deteccion:off}") String deteccion) {
        this.registro = registro;
        this.indice = "on".equalsIgnoreCase(deteccion);
        this.ttlMs = ttlSeg * 1000;
        this.hiloUnico = new ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS, colaOperacion,
            r -> new Thread(r, "hilo-unico-bd-bloqueo"));
        this.liberacion = Metricas.timerLargo(registro, "taq_bloqueo_liberacion_seconds");
        this.esperaCola = Metricas.timer(registro, "taq_cola_operacion_espera_seconds");
        this.conflictoConfirmada = Counter.builder("taq_conflicto_total").tag("resultado", "confirmada").register(registro);
        this.conflictoCancelada = Counter.builder("taq_conflicto_total").tag("resultado", "cancelada").register(registro);
        registro.gauge("taq_conflicto_pico_misma_silla", this,
            b -> System.currentTimeMillis() - b.picoEn > RETENCION_PICO_MS ? 0 : b.picoMismaSilla);
        registro.gauge("taq_rafaga_aprobadas", this, b -> System.currentTimeMillis() - b.rafagaUlt > RETENCION_PICO_MS ? 0 : b.rafagaAprobadas);
        registro.gauge("taq_rafaga_canceladas", this, b -> System.currentTimeMillis() - b.rafagaUlt > RETENCION_PICO_MS ? 0 : b.rafagaCanceladas);
        this.opsBloquear = Counter.builder("taq_bloqueo_ops_total").tag("op", "bloquear").register(registro);
        this.opsVender = Counter.builder("taq_bloqueo_ops_total").tag("op", "vender").register(registro);
        this.liberadosPorVencimiento = Counter.builder("taq_bloqueo_liberados_total").register(registro);
        // Métricas de EXP-3: solo existen (y se exponen) con la detección activa.
        this.liberadosAtaque = indice ? Counter.builder("taq_bloqueo_liberados_ataque_total").register(registro) : null;
        this.liberacionAtaque = indice ? Metricas.timerFino(registro, "taq_liberacion_ataque_seconds") : null;
        this.operacionAtaque = indice ? Metricas.timerFino(registro, "taq_liberacion_ataque_operacion_seconds") : null;
        registro.gauge("taq_cola_operacion_profundidad", colaOperacion, LinkedBlockingQueue::size);
        io.micrometer.core.instrument.FunctionCounter.builder("taq_hilo_unico_ocupado_nanos", ocupadoNanos, AtomicLong::doubleValue).register(registro);
        registro.gauge("taq_bloqueos_activos", this, b -> b.activos);
        vencimiento.scheduleWithFixedDelay(() -> {
            try { hiloUnico.execute(this::expirarVencidos); } catch (Exception ignored) {}
        }, 1, 1, TimeUnit.SECONDS);
    }

    private volatile int activos = 0;

    /** Envía una operación a la cola y espera su resultado (el hilo único la ejecuta). */
    private <T> T enHiloUnico(Callable<T> op) throws Exception {
        final long encolado = System.nanoTime();
        java.util.concurrent.FutureTask<T> f = new java.util.concurrent.FutureTask<>(() -> {
            long t0 = System.nanoTime();
            esperaCola.record(t0 - encolado, TimeUnit.NANOSECONDS);
            try { return op.call(); } finally { ocupadoNanos.addAndGet(System.nanoTime() - t0); }
        });
        hiloUnico.execute(f);
        return f.get(30, TimeUnit.SECONDS);
    }

    public Map<String, Object> bloquear(String solicitudId, String comprador, List<Integer> asientos) throws Exception {
        opsBloquear.increment();
        return enHiloUnico(() -> {
            long ahora = System.currentTimeMillis();
            if (!revocados.isEmpty() && revocados.contains(comprador)) {      // EXP-3: solicitud en vuelo de una cuenta ya revocada
                Map<String, Object> rv = new LinkedHashMap<>();
                rv.put("resultado", "CUENTA_REVOCADA");
                return rv;
            }
            registrarLlegadas(asientos, ahora);
            // 1) Revisión de todo el grupo: si uno solo no está libre, no se bloquea ninguno (todo o nada).
            for (int a : asientos) {
                if (vendidos.containsKey(a)) { anotarRafaga(ahora, null); return contar(rechazo(solicitudId, "VENDIDO", a)); }
                Bloqueo b = bloqueados.get(a);
                if (b != null) {
                    if (b.venceEn() <= ahora) liberar(a, b, ahora);       // vencido: se libera aquí mismo
                    else {
                        // Rechazo por conflicto simultáneo: el bloqueo que ganó es reciente (misma ráfaga).
                        if (ahora - b.bloqueadoEn() < VENTANA_CONFLICTO_MS) {
                            conflictoCancelada.increment();
                            if (b.conflicto().compareAndSet(false, true)) conflictoConfirmada.increment();
                            anotarRafaga(ahora, b);
                        }
                        return contar(rechazo(solicitudId, "NO_DISPONIBLE", a));
                    }
                }
            }
            // 2) Todos libres: se bloquean todos.
            var marca = new java.util.concurrent.atomic.AtomicBoolean();
            var marcaRafaga = new java.util.concurrent.atomic.AtomicBoolean();   // una sola marca por grupo ganador
            for (int a : asientos) {
                bloqueados.put(a, new Bloqueo(solicitudId, comprador, ahora, ahora + ttlMs, marca, marcaRafaga));
                if (indice) porComprador.computeIfAbsent(comprador, k -> new HashSet<>()).add(a);
                auditoria.add(evento("BLOQUEO", a, solicitudId, comprador, ahora));
            }
            activos = bloqueados.size();
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("resultado", "OK");
            r.put("bloqueadoEn", ahora);
            r.put("venceEn", ahora + ttlMs);
            return contar(r);
        });
    }

    public Map<String, Object> vender(String solicitudId, String comprador, List<Integer> asientos) throws Exception {
        opsVender.increment();
        return enHiloUnico(() -> {
            long ahora = System.currentTimeMillis();
            for (int a : asientos) {
                Bloqueo b = bloqueados.get(a);
                if (b == null || !b.comprador().equals(comprador) || b.venceEn() <= ahora) {
                    return rechazo(solicitudId, "BLOQUEO_INVALIDO", a);
                }
            }
            for (int a : asientos) {
                bloqueados.remove(a);
                if (indice) quitarDelIndice(comprador, a);
                vendidos.put(a, comprador);
                auditoria.add(evento("VENTA", a, solicitudId, comprador, ahora));
            }
            activos = bloqueados.size();
            return Map.<String, Object>of("resultado", "OK", "vendidoEn", ahora);
        });
    }

    private void expirarVencidos() {
        long ahora = System.currentTimeMillis();
        long t0 = System.nanoTime();
        Iterator<Map.Entry<Integer, Bloqueo>> it = bloqueados.entrySet().iterator();
        List<Map.Entry<Integer, Bloqueo>> vencidos = new ArrayList<>();
        while (it.hasNext()) {
            Map.Entry<Integer, Bloqueo> e = it.next();
            if (e.getValue().venceEn() <= ahora) vencidos.add(e);
        }
        for (Map.Entry<Integer, Bloqueo> e : vencidos) liberar(e.getKey(), e.getValue(), ahora);
        activos = bloqueados.size();
        ocupadoNanos.addAndGet(System.nanoTime() - t0);
    }

    private void liberar(int asiento, Bloqueo b, long ahora) {
        bloqueados.remove(asiento);
        if (indice) quitarDelIndice(b.comprador(), asiento);
        liberadosPorVencimiento.increment();
        liberacion.record(ahora - b.bloqueadoEn(), TimeUnit.MILLISECONDS);
        auditoria.add(evento("LIBERACION", asiento, b.solicitudId(), b.comprador(), ahora));
    }

    private void quitarDelIndice(String comprador, int asiento) {
        Set<Integer> s = porComprador.get(comprador);
        if (s != null) { s.remove(asiento); if (s.isEmpty()) porComprador.remove(comprador); }
    }

    /**
     * EXP-3 (S-2): libera de golpe todo lo que retiene un comprador, pasando por la cola del hilo único (no vende; solo libera
     * lo que sigue bloqueado). Con "revocar" las reservas nuevas de ese comprador se rechazan desde ya. Devuelve asientos y órdenes.
     */
    public Map<String, Object> liberarComprador(String comprador, boolean revocar) throws Exception {
        final long total0 = System.nanoTime();
        try {
            return enHiloUnico(() -> {
                long t0 = System.nanoTime();
                long ahora = System.currentTimeMillis();
                if (revocar) revocados.add(comprador);
                List<Integer> candidatos = new ArrayList<>();
                if (indice) {
                    Set<Integer> s = porComprador.remove(comprador);
                    if (s != null) candidatos.addAll(s);
                } else {   // sin índice (detección apagada): recorrido completo; solo para pruebas
                    for (var e : bloqueados.entrySet()) if (e.getValue().comprador().equals(comprador)) candidatos.add(e.getKey());
                }
                java.util.Collections.sort(candidatos);
                List<Integer> liberados = new ArrayList<>();
                Map<String, List<Integer>> ordenes = new java.util.LinkedHashMap<>();
                for (int a : candidatos) {
                    Bloqueo b = bloqueados.get(a);
                    if (b == null || !b.comprador().equals(comprador)) continue;   // ya no está bloqueado por él
                    bloqueados.remove(a);
                    liberados.add(a);
                    ordenes.computeIfAbsent(b.solicitudId(), k -> new ArrayList<>()).add(a);
                    auditoria.add(evento("LIBERACION_ATAQUE", a, b.solicitudId(), comprador, ahora));
                }
                activos = bloqueados.size();
                if (liberadosAtaque != null) liberadosAtaque.increment(liberados.size());
                List<Map<String, Object>> lista = new ArrayList<>();
                ordenes.forEach((sol, as) -> lista.add(Map.of("solicitudId", sol,
                    "asientos", as.stream().map(String::valueOf).collect(java.util.stream.Collectors.joining("-")))));
                long ns = System.nanoTime() - t0;
                if (operacionAtaque != null) operacionAtaque.record(ns, TimeUnit.NANOSECONDS);
                Map<String, Object> r = new LinkedHashMap<>();
                r.put("resultado", "OK"); r.put("comprador", comprador); r.put("liberados", liberados.size());
                r.put("asientos", liberados); r.put("ordenes", lista); r.put("operacion_ms", ns / 1e6);
                return r;
            });
        } finally {
            if (liberacionAtaque != null) liberacionAtaque.record(System.nanoTime() - total0, TimeUnit.NANOSECONDS);   // incluye la espera en cola
        }
    }

    /** EXP-3: cuántos asientos retiene cada comprador (por el hilo único: es el estado real). */
    public Map<String, Object> retenidos(List<String> compradores) throws Exception {
        return enHiloUnico(() -> {
            Map<String, Object> r = new LinkedHashMap<>();
            for (String c : compradores) {
                int n;
                if (indice) { Set<Integer> s = porComprador.get(c); n = s == null ? 0 : s.size(); }
                else { n = 0; for (Bloqueo b : bloqueados.values()) if (b.comprador().equals(c)) n++; }
                r.put(c, n);
            }
            return Map.<String, Object>of("ahora", System.currentTimeMillis(), "retenidos", r);
        });
    }

    public Map<String, Object> estado() throws Exception {
        return enHiloUnico(() -> {
            List<Map<String, Object>> bl = new ArrayList<>();
            bloqueados.forEach((a, b) -> bl.add(Map.of("asiento", a, "solicitudId", b.solicitudId(),
                "comprador", b.comprador(), "bloqueadoEn", b.bloqueadoEn(), "venceEn", b.venceEn())));
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("ahora", System.currentTimeMillis());
            r.put("ttlMs", ttlMs);
            r.put("bloqueados", bl);
            r.put("vendidos", new HashMap<>(vendidos));
            return r;
        });
    }

    public List<Map<String, Object>> auditoria() throws Exception {
        return enHiloUnico(() -> new ArrayList<>(auditoria));
    }

    /** Acumula la ráfaga en curso: cada rechazo suma una cancelada y el primer rechazo de un bloqueo suma su aprobada. */
    private void anotarRafaga(long ahora, Bloqueo ganador) {
        if (ahora - rafagaUlt > VENTANA_CONFLICTO_MS) { rafagaAprobadas = 0; rafagaCanceladas = 0; }
        rafagaUlt = ahora;
        rafagaCanceladas++;
        if (ganador != null && ganador.conflicto().get() && !ganador.contada().getAndSet(true)) rafagaAprobadas++;
    }

    /** Cuántas solicitudes llegaron a la misma silla en los últimos 2 s; guarda el pico para el tablero. */
    private void registrarLlegadas(List<Integer> asientos, long ahora) {
        for (int a : asientos) {
            var q = llegadas.computeIfAbsent(a, k -> new java.util.ArrayDeque<>());
            while (!q.isEmpty() && ahora - q.peekFirst() > VENTANA_CONFLICTO_MS) q.pollFirst();
            q.addLast(ahora);
            int n = q.size();
            if (n >= 2 && (n >= picoMismaSilla || ahora - picoEn > RETENCION_PICO_MS)) { picoMismaSilla = n; picoEn = ahora; }
        }
    }

    /** Cuenta cada decisión de bloqueo; los rechazos también por silla (solo sillas en disputa, pocas series). */
    private Map<String, Object> contar(Map<String, Object> r) {
        String res = String.valueOf(r.get("resultado"));
        String motivo = r.containsKey("motivo") ? String.valueOf(r.get("motivo")) : "-";
        Counter.builder("taq_bloqueo_decision_total").tag("resultado", res).tag("motivo", motivo).register(registro).increment();
        if (r.containsKey("asiento")) {
            Counter.builder("taq_bloqueo_rechazo_asiento_total").tag("asiento", String.valueOf(r.get("asiento")))
                .tag("motivo", motivo).register(registro).increment();
        }
        return r;
    }

    private static Map<String, Object> rechazo(String id, String motivo, int asiento) {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("resultado", "NO_DISPONIBLE");
        r.put("motivo", motivo);
        r.put("asiento", asiento);
        return r;
    }

    private static Map<String, Object> evento(String tipo, int asiento, String sol, String comprador, long ts) {
        Map<String, Object> e = new LinkedHashMap<>();
        e.put("tipo", tipo); e.put("asiento", asiento); e.put("solicitudId", sol);
        e.put("comprador", comprador); e.put("ts", ts);
        return e;
    }
}
