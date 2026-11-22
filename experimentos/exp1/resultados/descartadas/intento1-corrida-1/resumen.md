# EXP-1 — Corrida 1 (semilla 1)

| ASR | Resultado | Medida |
|---|---|---|
| **L-1** (p95 ≤ 150 ms) | ✅ cumple | p95 gateway = **132.1 ms** · p95 cliente = 10.0 ms · 97.47 % de las reservas ≤ 150 ms |
| **D-3** (0 asientos con más de una reserva) | ✅ cumple | 0 asientos con doble reserva · 0 bloqueos parciales · 248 de 248 conflictos con el resultado esperado |
| Vencimiento a los 8 min | ❌ no cumple | revisión 4 min rechazada 1496/1496 · revisión >8 min exitosa 79/717 · liberación real mín/p50/máx = 480.001/480.547/481.797 s |

**Carga:** 5189 llegadas normales y 248 conflictos programados (60 s de calentamiento + 720 s de tráfico). Solicitudes de reservar enviadas: 9253; errores técnicos: 0; confirmaciones exitosas: 2484/2484.

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
