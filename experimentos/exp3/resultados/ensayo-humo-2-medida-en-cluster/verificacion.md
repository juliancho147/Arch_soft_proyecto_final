# EXP-3 — verificación de la corrida

**Resultado global: ✅ cumple**

5 ataques, 100 bots, 400 solicitudes de bots, 300 asientos retenidos por bots.

## Criterios

| Criterio | Resultado |
|---|---|
| todos los ataques detectados | ✅ |
| todos los bots marcados | ✅ |
| compradores legitimos marcados 0 | ✅ |
| cuentas legitimas revocadas 0 | ✅ |
| asientos de bots retenidos al final 0 | ✅ |
| asientos liberados igual a los obtenidos | ✅ |
| ordenes canceladas igual a los obtenidos | ✅ |
| cuentas revocadas igual a bots | ✅ |
| S1 p95 dentro del limite | ✅ |
| S2 p95 dentro del limite | ✅ |

## S-1 detección (límite 100 ms) y S-2 recuperación (límite 300 ms), p95 por fase

| Fase | Detección p95 Prometheus | Detección p95 auditoría | Recuperación p95 medida independiente | Recuperación p95 interna (auditoría) | Recuperación p95 Prometheus |
|---|---|---|---|---|---|
| normal | 4.8 ms ✅ | 2.0 ms | 32.5 ms ✅ | 19.1 ms | 18.3 ms |
| pico | 4.6 ms ✅ | 2.0 ms | 27.2 ms ✅ | 18.0 ms | 17.5 ms |

La detección de Prometheus incluye el INSERT en bd_auditoria; la de la auditoría resta el instante previo al INSERT (por eso es algo menor).

## Ataques

| Ataque | Fase | Bots | Marcados | Detectado | Completo |
|---|---|---|---|---|---|
| A1 | normal | 20 | 20 | ✅ | ✅ |
| A2 | normal | 20 | 20 | ✅ | ✅ |
| A3 | normal | 20 | 20 | ✅ | ✅ |
| A4 | pico | 20 | 20 | ✅ | ✅ |
| A5 | pico | 20 | 20 | ✅ | ✅ |

## Datos adicionales

- Solicitudes fraudulentas por bot que pasaron antes de la marca: promedio 3.0, p95 3.0, máx 3.
- Compradores legítimos marcados: 0 ; legítimos con respuesta CUENTA_REVOCADA: 0; errores técnicos de legítimos: 0.
- Asientos obtenidos por bots 300 · liberados (auditoría) 300 · aún bloqueados al final 0.
- Órdenes canceladas (bots / otras): 300 / 0 · cuentas revocadas Postgres (bots / otras): 100 / 0 · Redis: 100.
- Medida independiente de recuperación: sí; seguimientos sin completar: 0.

## Tráfico legítimo (p95 de reservar, bitácora del generador)

| Fase | Durante recuperaciones (n) | p95 durante | Fuera de recuperaciones (n) | p95 fuera |
|---|---|---|---|---|
| normal | 64 | 12.8 ms | 346 | 23.0 ms |
| pico | 297 | 9.0 ms | 1138 | 11.0 ms |

## Colas y descartes (Prometheus)

| Fase | cola_evento_trafico máx | cola_operacion máx | cola_alerta máx | eventos descartados | rechazos cuenta revocada |
|---|---|---|---|---|---|
| normal | 0.0 | 0.0 | 0.0 | 0.0 | 11.7 |
| pico | 0.0 | 0.0 | 0.0 | 0.0 | 40.5 |
