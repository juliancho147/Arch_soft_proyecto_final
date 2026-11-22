# EXP-2 — Ejecución 1 (local, tope 5 réplicas)

**Validez: ⚠️ NO válida (el generador de carga se atrasó; no usar para concluir).** Atraso del generador p95 = 125850 ms.

| ASR | Resultado | Medida |
|---|---|---|
| **E-1** (p95 < 250 ms en el pico, sin perder solicitudes) | ❌ no cumple | p95 pico = **3065.5 ms** (tras equilibrio n/d ms) · cliente 10001 ms · 1544.0 solicitudes/min · rechazos por cola llena 0.0 · errores técnicos 0.0 |
| **Equilibrio** | ver réplicas | nodo-entrada → 0 (máx. 4), nodo-pasarela → 1 (máx. 3), nodo-reserva → 1 (máx. 5); réplicas estables desde el segundo 1130 |
| **Hilo único** | sin cuello de botella | máx. 209.1 ops/s · ocupado máx. 5.9 % · cola máx. 9.0 |
| **D-3** (0 dobles reservas, todo o nada) | ❌ no cumple | dobles 0 · parciales 27621 · conflictos con resultado esperado 1204/4718 · 4 min rechazadas 979/7137 · 8 min exitosas 55/7106 |

Detalle: [metricas.md](metricas.md) · [verificacion.md](verificacion.md) · `bitacora.csv` · `prometheus/*.json` · `tablero-grafana.json`.
