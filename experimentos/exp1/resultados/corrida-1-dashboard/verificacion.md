# Verificación D-3 — corrida-1-dashboard

**Veredicto D-3: CUMPLE ✅**

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Asientos con más de una reserva (auditoría de `bd_bloqueo`) | 0 | 0 |
| Asientos con más de una reserva (bitácora del cliente) | 0 | 0 |
| Asientos vendidos más de una vez (`reserva_log`) | 0 | 0 |
| Asientos bloqueados dos veces dentro del TTL (`reserva_log`) | 0 | 0 |
| Bloqueos parciales (todo o nada roto) | 0 | 0 |
| Bloqueos sin OK en el cliente | 0 | 0 |
| Conflictos con el resultado esperado | 248 de 248 | 248 de 248 |
| Vendidos en `reserva_log` = vendidos en `bd_bloqueo` | iguales | 3635 = 3635 |

## Conflictos por tipo

| Tipo | Conflictos | Con resultado esperado | Solicitudes |
|---|---|---|---|
| CONF_GRUPOS_CRUZADOS | 86 | 86 | 643 |
| CONF_MISMO_ASIENTO | 81 | 81 | 624 |
| CONF_VENDIDO | 81 | 81 | 584 |

## Vencimiento de bloqueos abandonados

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Revisión a los 4 min rechazada | todas | 1177 de 1177 |
| Revisión pasados los 8 min exitosa | todas | 717 de 717 |
| Bloqueos liberados por vencimiento | — | 1015 |
| Tiempo real bloqueo→liberación (mín / p50 / máx, s) | ≈ 480 | 480.00 / 480.52 / 481.00 |

## Volumen de la corrida

| Dato | Valor |
|---|---|
| Solicitudes de reservar (normales + conflictos + revisiones) | 8934 |
| Llegadas normales / con éxito | 5189 / 5189 |
| Confirmaciones / con éxito | 3693 / 3635 |
| Errores técnicos (5xx, timeouts, cola llena) | 58 |
| Asientos vendidos | 3635 |
| Bloqueos activos al terminar | 1707 |
