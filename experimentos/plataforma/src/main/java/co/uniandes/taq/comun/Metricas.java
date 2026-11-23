package co.uniandes.taq.comun;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

public final class Metricas {
    // Cubetas pensadas para el ASR: 150 ms es un borde exacto.
    private static final Duration[] SLO_MS = {
        Duration.ofMillis(5), Duration.ofMillis(10), Duration.ofMillis(20), Duration.ofMillis(30),
        Duration.ofMillis(50), Duration.ofMillis(75), Duration.ofMillis(100), Duration.ofMillis(125),
        Duration.ofMillis(150), Duration.ofMillis(200), Duration.ofMillis(300), Duration.ofMillis(500),
        Duration.ofSeconds(1), Duration.ofSeconds(2), Duration.ofSeconds(5)
    };
    private Metricas() {}

    public static Timer timer(MeterRegistry r, String nombre, String... tags) {
        return Timer.builder(nombre).serviceLevelObjectives(SLO_MS).tags(tags).register(r);
    }

    /** EXP-3: cubetas finas en milisegundos con los bordes de los ASR (100 ms para S-1 y 300 ms para S-2). */
    private static final long[] FINO_MS = {1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200, 250, 300, 400, 500, 750, 1000, 2000, 5000};

    public static Timer timerFino(MeterRegistry r, String nombre, String... tags) {
        Duration[] d = new Duration[FINO_MS.length];
        for (int i = 0; i < d.length; i++) d[i] = Duration.ofMillis(FINO_MS[i]);
        return Timer.builder(nombre).serviceLevelObjectives(d).tags(tags).register(r);
    }

    /** Para duraciones largas (liberación de bloqueos): de segundos a minutos. */
    public static Timer timerLargo(MeterRegistry r, String nombre, String... tags) {
        return Timer.builder(nombre)
            .serviceLevelObjectives(Duration.ofSeconds(60), Duration.ofSeconds(240), Duration.ofSeconds(470),
                Duration.ofSeconds(480), Duration.ofSeconds(481), Duration.ofSeconds(482),
                Duration.ofSeconds(485), Duration.ofSeconds(490), Duration.ofSeconds(600))
            .tags(tags).register(r);
    }
}
