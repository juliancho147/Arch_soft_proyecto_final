# EXP-2 — métricas de la ejecución

**E-1 (p95 < 250 ms durante el pico, sin perder solicitudes): ❌ no cumple**

| Medida | Valor |
|---|---|
| p95 en los 15 min del pico (con arranque de réplicas) | 3065.5 ms |
| p95 después del equilibrio | n/d ms |
| % de reservas ≤ 200 ms / ≤ 300 ms en el pico | 65.3 % / 70.5 % |
| p95 que ve el generador de carga | 10001 ms |
| Solicitudes en el pico | 23159.6 (≈ 1544.0/min) |
| Rechazos por cola llena | 0.0 |
| Errores técnicos | 0.0 |
| Equilibrio de réplicas desde | 1130 s del inicio |
| Hilo único: ops/s máx / prom · ocupado máx · cola máx | 209.1 / 51.2 · 5.9 % · 9.0 |
| Atraso del generador (p95) | 125850 ms → ejecución NO válida |

## Réplicas por pod

| Pod | Máximo | Final | Último cambio |
|---|---|---|---|
| nodo-entrada | 4 | 0 | 1130 s |
| nodo-pasarela | 3 | 1 | 740 s |
| nodo-reserva | 5 | 1 | 860 s |
