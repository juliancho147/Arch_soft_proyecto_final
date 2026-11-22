# EXP-2 — métricas de la ejecución

**E-1 (p95 < 250 ms durante el pico, sin perder solicitudes): ✅ cumple**

| Medida | Valor |
|---|---|
| p95 en los 1 min del pico (con arranque de réplicas) | 8.5 ms |
| p95 después del equilibrio | 8.5 ms |
| % de reservas ≤ 200 ms / ≤ 300 ms en el pico | 100.0 % / 100.0 % |
| p95 que ve el generador de carga | 9 ms |
| Solicitudes en el pico | 1960.4 (≈ 1960.4/min) |
| Rechazos por cola llena | 0.0 |
| Errores técnicos | 0 |
| Equilibrio de réplicas desde | 0 s del inicio |
| Hilo único: ops/s máx / prom · ocupado máx · cola máx | 49.4 / 41.3 · 0.1 % · 0.0 |
| Atraso del generador (p95) | 3 ms → ejecución válida |

## Réplicas por pod

| Pod | Máximo | Final | Último cambio |
|---|---|---|---|
| nodo-entrada | 1 | 1 | 0 s |
| nodo-pasarela | 1 | 1 | 0 s |
| nodo-reserva | 1 | 1 | 0 s |
