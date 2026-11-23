# EXP-2 — Ejecución 1 (AWS EKS, perfil por tramos 10 min, tope 8 réplicas)

**Validez: ✅ válida.** Atraso del generador p95 = 2 ms.

| ASR | Resultado | Medida |
|---|---|---|
| **E-1** (p95 < 250 ms en el pico, sin perder solicitudes) | ✅ cumple | p95 pico = **7.3 ms** (tras equilibrio n/d ms) · cliente 12 ms · 17501.7 solicitudes/min · rechazos por cola llena 0.0 · errores técnicos 0 |
| **Equilibrio** | ver réplicas | nodo-entrada → 2 (máx. 2), nodo-pasarela → 1 (máx. 2), nodo-reserva → 2 (máx. 2); réplicas estables desde el segundo 615 |
| **Hilo único** | sin cuello de botella | máx. 602.4 ops/s · ocupado máx. 0.9 % · cola máx. 1.0 |
| **D-3** (0 dobles reservas, todo o nada) | ✅ cumple | dobles 0 · parciales 0 · conflictos con resultado esperado 5492/5492 · 4 min rechazadas 19611/19611 · 8 min exitosas 4944/4944 |

**Por fase**

| Fase | Solicitudes/min | p95 | Errores | Réplicas máx. |
|---|---|---|---|---|
| pico8k | 7859.9 | 9.6 ms | 0 | entrada 2, pasarela 1, reserva 2 |
| ascenso | 14826.9 | 6.5 ms | 0 | entrada 2, pasarela 2, reserva 2 |
| meseta20k | 23853.7 | 7.2 ms | 0 | entrada 2, pasarela 2, reserva 2 |

Detalle: [metricas.md](metricas.md) · [verificacion.md](verificacion.md) · `bitacora.csv` · `prometheus/*.json` · `tablero-grafana.json`.
