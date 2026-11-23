# Verificación D-3 — corrida-1

**Veredicto D-3: CUMPLE ✅**

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Asientos con más de una reserva (auditoría de `bd_bloqueo`) | 0 | 0 |
| Asientos con más de una reserva (bitácora del cliente) | 0 | 0 |
| Asientos vendidos más de una vez (`reserva_log`) | 0 | 0 |
| Asientos bloqueados dos veces dentro del TTL (`reserva_log`) | 0 | 0 |
| Bloqueos parciales (todo o nada roto) | 0 | 0 |
| Bloqueos sin OK en el cliente | 0 | 0 |
| Conflictos con el resultado esperado | 5492 de 5492 | 5492 de 5492 |
| Vendidos en `reserva_log` = vendidos en `bd_bloqueo` | iguales | 76567 = 76567 |

## Conflictos por tipo

| Tipo | Conflictos | Con resultado esperado | Solicitudes |
|---|---|---|---|
| CONF_GRUPOS_CRUZADOS | 1808 | 1808 | 13632 |
| CONF_MISMO_ASIENTO | 1896 | 1896 | 14212 |
| CONF_VENDIDO | 1788 | 1788 | 13401 |

## Vencimiento de bloqueos abandonados

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Revisión a los 4 min rechazada | todas | 19611 de 19611 |
| Revisión pasados los 8 min exitosa | todas | 4944 de 4944 |
| Bloqueos liberados por vencimiento | — | 47246 |
| Tiempo real bloqueo→liberación (mín / p50 / máx, s) | ≈ 480 | 480.00 / 480.50 / 481.00 |

## Volumen de la corrida

| Dato | Valor |
|---|---|
| Solicitudes de reservar (normales + conflictos + revisiones) | 174990 |
| Llegadas normales / con éxito | 109190 / 109190 |
| Confirmaciones / con éxito | 76578 / 76567 |
| Errores técnicos (5xx, timeouts, cola llena) | 11 |
| Asientos vendidos | 76567 |
| Bloqueos activos al terminar | 0 |
