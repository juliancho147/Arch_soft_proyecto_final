# Experimentos TAQ

Implementación y resultados de los experimentos definidos en [`../Plan-Experimentos-TAQ.md`](../Plan-Experimentos-TAQ.md).

| Carpeta | Contenido |
|---|---|
| [`plataforma/`](plataforma) | Código Java 17 (Spring Boot) de los componentes: gateway, nodo de reserva, `bd_bloqueo`, pasarela simulada y verificador. Una sola imagen; el rol se elige con `TAQ_ROLE`. |
| [`exp1/`](exp1) | EXP-1 (L-1 y D-3): manifiestos de Kubernetes, plan de JMeter, scripts y resultados. |

## Convención de resultados

Cada experimento deja sus resultados en `expN/resultados/`, en Markdown y JSON para poder armar después el tablero de la presentación:

```
expN/resultados/
├── resumen-expN.md / .json     ← consolidado y veredicto por ASR  (fuente del tablero final)
├── entorno.md                  ← máquina, versiones y límites de recursos
└── corrida-K/
    ├── resumen.md              ← una página: veredicto y cifras clave
    ├── metricas.md / .json     ← latencias, CPU, memoria, colas
    ├── verificacion.md / .json ← comprobaciones de correctitud
    ├── graficas/*.png          ← gráficas listas para diapositivas
    ├── prometheus/*.json       ← series crudas (paso de 5 s)
    ├── tablero-grafana.json    ← tablero usado para seguir la corrida
    └── bitacora.csv, ejecucion.json, jmeter.jtl/.log   ← evidencia cruda
```

## Requisitos locales

Docker Desktop, `kind`, `kubectl`, JDK 21 (compila a Java 17), Maven y JMeter (Homebrew), y un entorno Python con `matplotlib` (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`).
