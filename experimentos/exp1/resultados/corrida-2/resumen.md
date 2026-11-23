# EXP-1 — Corrida 2 (semilla 2)

**Validez de la corrida: ✅ válida.** Atraso del generador de carga frente al calendario: p95 = 2 ms, máx. = 43 ms. Diferencia de solicitudes gateway vs. cliente: 0.19 %. Carga de la máquina (load average 1 min, antes → después): 9.95 → 13.51.

| ASR | Resultado | Medida |
|---|---|---|
| **L-1** (p95 ≤ 150 ms) | ✅ cumple | p95 gateway = **4.9 ms** · p95 cliente = 8.0 ms · 100.00 % de las reservas ≤ 150 ms |
| **D-3** (0 asientos con más de una reserva) | ✅ cumple | 0 asientos con doble reserva · 0 bloqueos parciales · 253 de 253 conflictos con el resultado esperado |
| Vencimiento a los 8 min | ✅ cumple | revisión 4 min rechazada 1217/1217 · revisión >8 min exitosa 707/707 · liberación real mín/p50/máx = 480.0/480.468/481.0 s |

**Carga:** 5237 llegadas normales y 253 conflictos programados (60 s de calentamiento + 720 s de tráfico). Solicitudes de reservar enviadas: 9042; errores técnicos: 0; confirmaciones exitosas: 3680/3680.

## Archivos de esta corrida

| Archivo | Contenido |
|---|---|
| [metricas.md](metricas.md) / `metricas.json` | Latencia (gateway y cliente), CPU, memoria, colas, hilo único |
| [verificacion.md](verificacion.md) / `verificacion.json` | Comprobaciones de D-3 y del vencimiento |
| `bitacora.csv` | Cada solicitud enviada: asiento, comprador, resultado y hora |
| `ejecucion.json` | Semilla, marcas de tiempo y tamaño del calendario |
| `jmeter.jtl`, `jmeter.log` | Salida cruda de JMeter |
| `graficas/*.png` | Gráficas de la corrida (p95, colas, hilo único, CPU, memoria) |
| `prometheus/*.json` | Series crudas de Prometheus (paso de 5 s) |
| `tablero-grafana.json` | Tablero de Grafana usado para seguir la corrida |
