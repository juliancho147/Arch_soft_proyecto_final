# EXP-1 — Resultados consolidados

**Hipótesis:** con la carga normal de reservas y una sola réplica, reservar cumple el tiempo de respuesta definido (L-1: p95 ≤ 150 ms) y, aun con conflictos inyectados al azar, solo una solicitud obtiene cada asiento, sin bloqueos parciales ni asientos con más de una reserva (D-3).

## Veredicto



| ASR | Corridas que cumplen | Veredicto |
|---|---|---|
| L-1 — p95 de reservar ≤ 150 ms | 3 de 3 | ✅ Cumple |
| D-3 — 0 asientos con más de una reserva | 3 de 3 | ✅ Cumple |
| Vencimiento a los 8 min | 3 de 3 | ✅ Cumple |

## Por corrida

| Corrida | Válida | Atraso gen. p95 (ms) | Semilla | Llegadas | Conflictos | Solicitudes de reservar | p50 gw (ms) | p95 gw (ms) | p99 gw (ms) | p95 cliente (ms) | % ≤ 150 ms | L-1 | D-3 | Vencimiento |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| corrida-1 | ✅ | 3 | 1 | 5189 | 248 | 8934 | 2.7 | **7.8** | 15.8 | 12.0 | 100.00 | ✅ | ✅ | ✅ |
| corrida-2 | ✅ | 2 | 2 | 5237 | 253 | 9042 | 2.6 | **4.9** | 9.4 | 8.0 | 100.00 | ✅ | ✅ | ✅ |
| corrida-3 | ✅ | 2 | 3 | 5352 | 247 | 9224 | 2.6 | **4.9** | 9.8 | 8.0 | 100.00 | ✅ | ✅ | ✅ |

**p95 del gateway** (la medida del ASR): promedio de las corridas = 5.9 ms, peor = 7.8 ms. Diferencia con el cliente: 3.4 ms de promedio.

## D-3 y vencimiento

| Corrida | Asientos con doble reserva | Bloqueos parciales | Conflictos con resultado esperado | Liberación real p50 / máx (s) | Errores técnicos |
|---|---|---|---|---|---|
| corrida-1 | 0 | 0 | 248 de 248 | 480.5 / 481.0 | 0 |
| corrida-2 | 0 | 0 | 253 de 253 | 480.5 / 481.0 | 0 |
| corrida-3 | 0 | 0 | 247 de 247 | 480.5 / 481.0 | 0 |

## Recursos y colas (ventana de tráfico normal)

| Corrida | Hilo único: ocupación prom. / máx. (%) | Operaciones/s en `bd_bloqueo` (prom.) | `cola_solicitud` máx. | `cola_operacion` máx. | CPU máx. de un componente (%) | Caché: tasa de acierto (%) |
|---|---|---|---|---|---|---|
| corrida-1 | 0.0 / 0.1 | 16.0 | 0.0 | 0.0 | 16.5 | 99.9 |
| corrida-2 | 0.0 / 0.0 | 16.1 | 0.0 | 0.0 | 13.1 | 99.9 |
| corrida-3 | 0.0 / 0.1 | 16.4 | 0.0 | 0.0 | 14.5 | 99.9 |

Detalle de cada corrida: `corrida-N/resumen.md`. Entorno y límites de recursos: [entorno.md](entorno.md).
