# Verificación D-3 — d3

**Veredicto D-3: CUMPLE ✅**

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Asientos con más de una reserva (auditoría de `bd_bloqueo`) | 0 | 0 |
| Asientos con más de una reserva (bitácora del cliente) | 0 | 0 |
| Asientos vendidos más de una vez (`reserva_log`) | 0 | 0 |
| Asientos bloqueados dos veces dentro del TTL (`reserva_log`) | 0 | 0 |
| Bloqueos parciales (todo o nada roto) | 0 | 0 |
| Bloqueos sin OK en el cliente | 0 | 0 |
| Conflictos con el resultado esperado | 82 de 82 | 82 de 82 |
| Vendidos en `reserva_log` = vendidos en `bd_bloqueo` | iguales | 1248 = 1248 |

## Conflictos por tipo

| Tipo | Conflictos | Con resultado esperado | Solicitudes |
|---|---|---|---|
| ATAQUE_BOT | 5 | 5 | 400 |
| CONF_GRUPOS_CRUZADOS | 25 | 25 | 184 |
| CONF_MISMO_ASIENTO | 28 | 28 | 214 |
| CONF_VENDIDO | 24 | 24 | 171 |

## Vencimiento de bloqueos abandonados

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Revisión a los 4 min rechazada | todas | 0 de 0 |
| Revisión pasados los 8 min exitosa | todas | 0 de 0 |
| Bloqueos liberados por vencimiento | — | 0 |

## Volumen de la corrida

| Dato | Valor |
|---|---|
| Solicitudes de reservar (normales + conflictos + revisiones) | 2755 |
| Llegadas normales / con éxito | 1786 / 1786 |
| Confirmaciones / con éxito | 1248 / 1248 |
| Errores técnicos (5xx, timeouts, cola llena) | 0 |
| Asientos vendidos | 1248 |
| Bloqueos activos al terminar | 672 |
