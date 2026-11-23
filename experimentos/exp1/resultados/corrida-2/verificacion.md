# Verificación D-3 — corrida-2

**Veredicto D-3: CUMPLE ✅**

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Asientos con más de una reserva (auditoría de `bd_bloqueo`) | 0 | 0 |
| Asientos con más de una reserva (bitácora del cliente) | 0 | 0 |
| Asientos vendidos más de una vez (`reserva_log`) | 0 | 0 |
| Asientos bloqueados dos veces dentro del TTL (`reserva_log`) | 0 | 0 |
| Bloqueos parciales (todo o nada roto) | 0 | 0 |
| Bloqueos sin OK en el cliente | 0 | 0 |
| Conflictos con el resultado esperado | 253 de 253 | 253 de 253 |
| Vendidos en `reserva_log` = vendidos en `bd_bloqueo` | iguales | 3680 = 3680 |

## Conflictos por tipo

| Tipo | Conflictos | Con resultado esperado | Solicitudes |
|---|---|---|---|
| CONF_GRUPOS_CRUZADOS | 83 | 83 | 632 |
| CONF_MISMO_ASIENTO | 86 | 86 | 628 |
| CONF_VENDIDO | 84 | 84 | 621 |

## Vencimiento de bloqueos abandonados

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Revisión a los 4 min rechazada | todas | 1217 de 1217 |
| Revisión pasados los 8 min exitosa | todas | 707 de 707 |
| Bloqueos liberados por vencimiento | — | 979 |
| Tiempo real bloqueo→liberación (mín / p50 / máx, s) | ≈ 480 | 480.00 / 480.47 / 481.00 |

## Volumen de la corrida

| Dato | Valor |
|---|---|
| Solicitudes de reservar (normales + conflictos + revisiones) | 9042 |
| Llegadas normales / con éxito | 5237 / 5237 |
| Confirmaciones / con éxito | 3680 / 3680 |
| Errores técnicos (5xx, timeouts, cola llena) | 0 |
| Asientos vendidos | 3680 |
| Bloqueos activos al terminar | 1733 |
