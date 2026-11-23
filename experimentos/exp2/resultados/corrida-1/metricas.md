# EXP-2 — métricas de la ejecución

**E-1 (p95 < 250 ms durante el pico, sin perder solicitudes): ✅ cumple**

| Medida | Valor |
|---|---|
| p95 en los 9 min del pico (con arranque de réplicas) | 7.3 ms |
| p95 después del equilibrio | n/d ms |
| % de reservas ≤ 200 ms / ≤ 300 ms en el pico | 100.0 % / 100.0 % |
| p95 que ve el generador de carga | 12 ms |
| Solicitudes en el pico | 166265.9 (≈ 17501.7/min) |
| Rechazos por cola llena | 0.0 |
| Errores técnicos | 0 |
| Equilibrio de réplicas desde | 615 s del inicio |
| Hilo único: ops/s máx / prom · ocupado máx · cola máx | 602.4 / 407.2 · 0.9 % · 1.0 |
| Atraso del generador (p95) | 2 ms → ejecución válida |

## Réplicas por pod

| Pod | Máximo | Final | Último cambio |
|---|---|---|---|
| nodo-entrada | 2 | 2 | 75 s |
| nodo-pasarela | 2 | 1 | 615 s |
| nodo-reserva | 2 | 2 | 75 s |

## Por fase

| Fase | Solicitudes/min | p95 | ≤200 ms | ≤300 ms | Errores | Réplicas máx. |
|---|---|---|---|---|---|---|
| pico8k (30–120 s) | 7859.9 | 9.6 ms | 100.0 % | 100.0 % | 0 | entrada 2, pasarela 1, reserva 2 |
| ascenso (120–360 s) | 14826.9 | 6.5 ms | 100.0 % | 100.0 % | 0 | entrada 2, pasarela 2, reserva 2 |
| meseta20k (360–600 s) | 23853.7 | 7.2 ms | 100.0 % | 100.0 % | 0 | entrada 2, pasarela 2, reserva 2 |
