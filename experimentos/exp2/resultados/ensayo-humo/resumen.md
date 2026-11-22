# EXP-2 — Ejecución 0 (local, tope 5 réplicas)

**Validez: ✅ válida.** Atraso del generador p95 = 2 ms.

| ASR | Resultado | Medida |
|---|---|---|
| **E-1** (p95 < 250 ms en el pico, sin perder solicitudes) | ✅ cumple | p95 pico = **7.6 ms** (tras equilibrio 7.6 ms) · cliente 12 ms · 1937.5 solicitudes/min · rechazos por cola llena 0.0 · errores técnicos 0 |
| **Equilibrio** | ver réplicas | nodo-entrada → 1 (máx. 1), nodo-pasarela → 1 (máx. 1), nodo-reserva → 1 (máx. 1); réplicas estables desde el segundo 0 |
| **Hilo único** | sin cuello de botella | máx. 49.3 ops/s · ocupado máx. 0.3 % · cola máx. 0.0 |
| **D-3** (0 dobles reservas, todo o nada) | ✅ cumple | dobles 0 · parciales 0 · conflictos con resultado esperado 86/86 · 4 min rechazadas 0/0 · 8 min exitosas 0/0 |

Detalle: [metricas.md](metricas.md) · [verificacion.md](verificacion.md) · `bitacora.csv` · `prometheus/*.json` · `tablero-grafana.json`.
