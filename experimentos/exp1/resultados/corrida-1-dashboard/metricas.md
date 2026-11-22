# Métricas L-1 — corrida-1-dashboard

**Corrida VÁLIDA ✅** — atraso del generador frente al calendario: p95 = 2 ms, máx. = 30 ms; diferencia de solicitudes gateway vs. cliente = 0.27 %; desfase de reloj de Prometheus = 0.00 s.

**Veredicto L-1: CUMPLE ✅** — p95 de reservar en el gateway = **8.4 ms** (ASR ≤ 150 ms), ventana de 720 s de tráfico normal (se excluye el minuto de calentamiento).

## Latencia de reservar

| Medición | Frontera | n | p50 (ms) | p95 (ms) | p99 (ms) | % ≤ 150 ms |
|---|---|---|---|---|---|---|
| **ASR — solo reservas exitosas** | gateway (Prometheus) | 5591 | 2.8 | **8.4** | 16.2 | 99.60 % |
| Todas las respuestas (éxito + rechazo) | gateway (Prometheus) | 8185 | 2.9 | 8.7 | 17.9 | 99.48 % |
| Solo exitosas | cliente (JMeter/bitácora) | 5586 | 5.0 | 12.0 | 21.0 | 99.59 % |
| Todas | cliente (JMeter/bitácora) | 8164 | 5.0 | 13.0 | 25.0 | 99.47 % |

- Diferencia del p95 (cliente − gateway, solo exitosas): **3.6 ms** (red local de kind + kube-proxy + cliente HTTP).
- El p95 del gateway se calcula con histogramas de Prometheus (cubetas en 100, 125, 150, 200 ms…), por lo que se interpola dentro de la cubeta; el porcentaje ≤ 150 ms es exacto porque 150 ms es un borde de cubeta.
- Tasa real medida en el gateway: 682 solicitudes de reservar por minuto (400 llegadas normales por minuto + las solicitudes de los conflictos).
- Resultados en la ventana: NO_DISPONIBLE = 2594, OK = 5591. Rechazos por cola llena: 0.

![p95](graficas/p95-reservar.png)

## Recursos y colas (ventana medida)

| Componente | CPU prom. (%) | CPU máx. (%) | Heap prom. (MB) | Heap máx. (MB) |
|---|---|---|---|---|
| bloqueo | 3.7 | 14.5 | 30.8 | 44.0 |
| gateway | 2.1 | 7.2 | 42.4 | 57.3 |
| pasarela | 2.1 | 6.2 | 26.6 | 34.5 |
| reserva | 3.5 | 43.2 | 60.5 | 150.2 |

| Indicador | Promedio | Máximo |
|---|---|---|
| Profundidad de `cola_solicitud` | 0.2 | 33.0 |
| Profundidad de `cola_operacion` (hilo único) | 0.0 | 1.0 |
| Profundidad de `cola_persistencia` | 0.0 | 0.0 |
| Ocupación del hilo único de `bd_bloqueo` (%) | 0.1 | 0.4 |
| Operaciones por segundo en `bd_bloqueo` | 15.9 | 20.9 |
| Bloqueos activos | 1,177.2 | 1,884.0 |

- Caché de asientos: 4738 aciertos y 1045 fallos (tasa de acierto 81.9 %).
- Operaciones en `bd_bloqueo` durante la ventana: bloquear = 8175, vender = 3357.
- CPU: porcentaje del proceso JVM (`process_cpu_usage`), no de la máquina.

![colas](graficas/colas.png)
![hilo único](graficas/hilo-unico.png)
![cpu](graficas/cpu.png)
![memoria](graficas/heap-mb.png)
![reservas por segundo](graficas/reservas-por-segundo.png)
![bloqueos activos](graficas/bloqueos-activos.png)
