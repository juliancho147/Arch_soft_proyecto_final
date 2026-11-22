# EXP-1 — Corrida 1 (semilla 1)

**Validez de la corrida: ✅ válida.** Atraso del generador de carga frente al calendario: p95 = 2 ms, máx. = 30 ms. Diferencia de solicitudes gateway vs. cliente: 0.27 %. Carga de la máquina (load average 1 min, antes → después): 17.23 → 13.45.

| ASR | Resultado | Medida |
|---|---|---|
| **L-1** (p95 ≤ 150 ms) | ✅ cumple | p95 gateway = **8.4 ms** · p95 cliente = 12.0 ms · 99.60 % de las reservas ≤ 150 ms |
| **D-3** (0 asientos con más de una reserva) | ✅ cumple | 0 asientos con doble reserva · 0 bloqueos parciales · 248 de 248 conflictos con el resultado esperado |
| Vencimiento a los 8 min | ✅ cumple | revisión 4 min rechazada 1177/1177 · revisión >8 min exitosa 717/717 · liberación real mín/p50/máx = 480.001/480.523/481.001 s |

**Carga:** 5189 llegadas normales y 248 conflictos programados (60 s de calentamiento + 720 s de tráfico). Solicitudes de reservar enviadas: 8934; errores técnicos: 58; confirmaciones exitosas: 3635/3693.

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
