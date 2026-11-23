# Experimento 3 desde el panel — resumen de la prueba

- Duración: **10 min 0 s** · ataques lanzados (cantidad y momentos aleatorios): **15** · cuentas atacantes inyectadas: **940**
- **S-1, p95 de detección: 4.8 ms** (límite 100 ms) → ✅ cumple
- **S-2, p95 de recuperación: 14.5 ms** (límite 300 ms) → ✅ cumple
- Compradores legítimos marcados: **0** (se espera 0) · asientos liberados 2720 · órdenes canceladas 1880 · cuentas revocadas 940
- Solicitudes fraudulentas que pasaron antes de la marca (promedio por cuenta): 3.6

## Por tipo de ataque (el tipo es la etiqueta `tipoAtacante` que declara el panel)

| Tipo | Ataques | Cuentas inyectadas | Cuentas marcadas | p95 detección | p95 recuperación |
|---|---|---|---|---|---|
| Bot individual | 4 | 400 | 400 | 3.7 ms | 11.6 ms |
| Granja de cuentas | 4 | 400 | 400 | 7.0 ms | 20.0 ms |
| Acaparador de asientos | 7 | 140 | 140 | 5.0 ms | 15.0 ms |

## Ataques lanzados

| # | Hora | Tipo | Cuentas | Solicitudes | OK | Rechazadas por cuenta revocada |
|---|---|---|---|---|---|---|
| A1 | 22:24:54 | Acaparador de asientos | 20 | 60 | 40 | 20 |
| A2 | 22:25:06 | Acaparador de asientos | 20 | 60 | 40 | 20 |
| A3 | 22:26:08 | Acaparador de asientos | 20 | 60 | 40 | 20 |
| A4 | 22:26:17 | Granja de cuentas | 100 | 200 | 100 | 100 |
| A5 | 22:27:04 | Bot individual | 100 | 400 | 300 | 100 |
| A6 | 22:27:20 | Acaparador de asientos | 20 | 60 | 40 | 20 |
| A7 | 22:29:31 | Bot individual | 100 | 400 | 300 | 100 |
| A8 | 22:29:38 | Acaparador de asientos | 20 | 60 | 40 | 20 |
| A9 | 22:29:45 | Bot individual | 100 | 400 | 300 | 100 |
| A10 | 22:30:25 | Granja de cuentas | 100 | 200 | 100 | 100 |
| A11 | 22:30:26 | Bot individual | 100 | 400 | 300 | 100 |
| A12 | 22:30:57 | Acaparador de asientos | 20 | 60 | 40 | 20 |
| A13 | 22:31:34 | Granja de cuentas | 100 | 200 | 100 | 100 |
| A14 | 22:32:29 | Acaparador de asientos | 20 | 60 | 40 | 20 |
| A15 | 22:32:43 | Granja de cuentas | 100 | 200 | 100 | 100 |

> Resumen rápido del panel con las métricas de Prometheus. La verificación completa (bitácora x auditoría x estado final) la hace `exp3/scripts/verificar_exp3.py`.
