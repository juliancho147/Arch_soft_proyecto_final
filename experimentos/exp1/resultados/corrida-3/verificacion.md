# Verificación D-3 — corrida-3

**Veredicto D-3: CUMPLE ✅**

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Asientos con más de una reserva (auditoría de `bd_bloqueo`) | 0 | 0 |
| Asientos con más de una reserva (bitácora del cliente) | 0 | 0 |
| Asientos vendidos más de una vez (`reserva_log`) | 0 | 0 |
| Asientos bloqueados dos veces dentro del TTL (`reserva_log`) | 0 | 0 |
| Bloqueos parciales (todo o nada roto) | 0 | 0 |
| Bloqueos sin OK en el cliente | 0 | 0 |
| Conflictos con el resultado esperado | 247 de 247 | 247 de 247 |
| Vendidos en `reserva_log` = vendidos en `bd_bloqueo` | iguales | 3697 = 3697 |

## Conflictos por tipo

| Tipo | Conflictos | Con resultado esperado | Solicitudes |
|---|---|---|---|
| CONF_GRUPOS_CRUZADOS | 79 | 79 | 588 |
| CONF_MISMO_ASIENTO | 72 | 72 | 558 |
| CONF_VENDIDO | 96 | 96 | 719 |

## Vencimiento de bloqueos abandonados

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Revisión a los 4 min rechazada | todas | 1278 de 1278 |
| Revisión pasados los 8 min exitosa | todas | 729 de 729 |
| Bloqueos liberados por vencimiento | — | 961 |
| Tiempo real bloqueo→liberación (mín / p50 / máx, s) | ≈ 480 | 480.00 / 480.54 / 481.00 |

## Volumen de la corrida

| Dato | Valor |
|---|---|
| Solicitudes de reservar (normales + conflictos + revisiones) | 9224 |
| Llegadas normales / con éxito | 5352 / 5352 |
| Confirmaciones / con éxito | 3697 / 3697 |
| Errores técnicos (5xx, timeouts, cola llena) | 0 |
| Asientos vendidos | 3697 |
| Bloqueos activos al terminar | 1816 |
