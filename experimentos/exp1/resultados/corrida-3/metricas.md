# Métricas L-1 — corrida-3

**Corrida VÁLIDA ✅** — atraso del generador frente al calendario: p95 = 2 ms, máx. = 34 ms; diferencia de solicitudes gateway vs. cliente = 0.10 %; desfase de reloj de Prometheus = 0.00 s.

**Veredicto L-1: CUMPLE ✅** — p95 de reservar en el gateway = **4.9 ms** (ASR ≤ 150 ms), ventana de 720 s de tráfico normal (se excluye el minuto de calentamiento).

## Latencia de reservar

| Medición | Frontera | n | p50 (ms) | p95 (ms) | p99 (ms) | % ≤ 150 ms |
|---|---|---|---|---|---|---|
| **ASR — solo reservas exitosas** | gateway (Prometheus) | 5718 | 2.6 | **4.9** | 9.8 | 100.00 % |
| Todas las respuestas (éxito + rechazo) | gateway (Prometheus) | 8421 | 2.6 | 5.0 | 11.5 | 100.00 % |
| Solo exitosas | cliente (JMeter/bitácora) | 5712 | 3.0 | 8.0 | 15.0 | 100.00 % |
| Todas | cliente (JMeter/bitácora) | 8413 | 3.0 | 9.0 | 17.0 | 100.00 % |

- Diferencia del p95 (cliente − gateway, solo exitosas): **3.1 ms** (red local de kind + kube-proxy + cliente HTTP).
- El p95 del gateway se calcula con histogramas de Prometheus (cubetas en 100, 125, 150, 200 ms…), por lo que se interpola dentro de la cubeta; el porcentaje ≤ 150 ms es exacto porque 150 ms es un borde de cubeta.
- Tasa real medida en el gateway: 702 solicitudes de reservar por minuto (400 llegadas normales por minuto + las solicitudes de los conflictos).
- Resultados en la ventana: NO_DISPONIBLE = 2702, OK = 5718. Rechazos por cola llena: 0.

![p95](graficas/p95-reservar.png)

## Recursos y colas (ventana medida)

| Componente | CPU prom. (%) | CPU máx. (%) | Heap prom. (MB) | Heap máx. (MB) |
|---|---|---|---|---|
| bloqueo | 2.9 | 14.5 | 32.1 | 45.7 |
| gateway | 1.1 | 2.4 | 77.5 | 115.8 |
| pasarela | 1.3 | 6.2 | 43.0 | 57.1 |
| reserva | 1.4 | 2.6 | 73.7 | 108.4 |

| Indicador | Promedio | Máximo |
|---|---|---|
| Profundidad de `cola_solicitud` | 0.0 | 0.0 |
| Profundidad de `cola_operacion` (hilo único) | 0.0 | 0.0 |
| Profundidad de `cola_persistencia` | 0.0 | 0.0 |
| Ocupación del hilo único de `bd_bloqueo` (%) | 0.0 | 0.1 |
| Operaciones por segundo en `bd_bloqueo` | 16.4 | 21.1 |
| Bloqueos activos | 1,168.3 | 1,987.0 |

- Caché de asientos: 5893 aciertos y 6 fallos (tasa de acierto 99.9 %).
- Operaciones en `bd_bloqueo` durante la ventana: bloquear = 8418, vender = 3411.
- CPU: porcentaje del proceso JVM (`process_cpu_usage`), no de la máquina.

![colas](graficas/colas.png)
![hilo único](graficas/hilo-unico.png)
![cpu](graficas/cpu.png)
![memoria](graficas/heap-mb.png)
![reservas por segundo](graficas/reservas-por-segundo.png)
![bloqueos activos](graficas/bloqueos-activos.png)
