# EXP-3 — verificación de la corrida

**Resultado global: ❌ no cumple (ver criterios)**

5 ataques, 108 bots, 304 solicitudes de bots, 244 asientos retenidos por bots.

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
| todos los ataques de cada tipo detectados | ✅ |
| S1 p95 dentro del limite | ❌ |
| S2 p95 dentro del limite | ✅ |

## S-1 detección (límite 100 ms) y S-2 recuperación (límite 300 ms), p95 por fase

| Fase | Detección p95 Prometheus | Detección p95 auditoría | Recuperación p95 medida independiente | Recuperación p95 interna (auditoría) | Recuperación p95 Prometheus |
|---|---|---|---|---|---|
| normal | 191.0 ms ❌ | 183.1 ms | 236.5 ms ✅ | 167.7 ms | 175.8 ms |
| pico | 98.2 ms ✅ | 96.7 ms | 63.5 ms ✅ | 47.2 ms | 47.5 ms |

La detección de Prometheus incluye el INSERT en bd_auditoria; la de la auditoría resta el instante previo al INSERT (por eso es algo menor).

## Tipos de ataque

El tipo lo **declara el generador** con la etiqueta `tipoAtacante` (no hay clasificador): esta tabla comprueba que cada tipo etiquetado se detectó con la regla esperada y mide S-1 y S-2 por tipo.

| Tipo | Ataques (detectados / inyectados) | Cuentas (marcadas / inyectadas) | Regla que disparó cada marca | Etiqueta en auditoría coincide | Solicitudes antes de la marca (prom / p95 / máx) | Detección p95 (auditoría / Prometheus) | Recuperación p95 (independiente / interna / Prometheus) |
|---|---|---|---|---|---|---|---|
| bot_individual | 2 / 2 ✅ | 40 / 40 | cuenta_frecuencia=40 | 40 / 40 | 3.0 / 3.0 / 3 | 1.0 ms ✅ / 3.0 ms | 21.2 ms ✅ / 10.2 ms / 10.0 ms |
| granja_cuentas | 2 / 2 ✅ | 60 / 60 | ip_frecuencia=40, ip_marcada=20 | 60 / 60 | 1.0 / 1.0 / 1 | 182.3 ms ❌ / 190.0 ms | 233.7 ms ✅ / 166.6 ms / 175.0 ms |
| acaparador | 1 / 1 ✅ | 8 / 8 | cuenta_asientos=8 | 8 / 8 | 2.0 / 2.0 / 2 | 1.0 ms ✅ / 4.2 ms | 27.8 ms ✅ / 14.9 ms / 18.0 ms |

Compradores legítimos marcados: 0 (cuentas legítimas observadas: 2355).

## Ataques

| Ataque | Fase | Tipo | Bots | Marcados | Detectado | Completo |
|---|---|---|---|---|---|---|
| A1 | normal | granja_cuentas | 30 | 30 | ✅ | ✅ |
| A2 | normal | acaparador | 8 | 8 | ✅ | ✅ |
| A3 | normal | bot_individual | 20 | 20 | ✅ | ✅ |
| A4 | pico | bot_individual | 20 | 20 | ✅ | ✅ |
| A5 | pico | granja_cuentas | 30 | 30 | ✅ | ✅ |

## Datos adicionales

- Solicitudes fraudulentas por bot que pasaron antes de la marca: promedio 1.8, p95 3.0, máx 3.
- Compradores legítimos marcados: 0 ; legítimos con respuesta CUENTA_REVOCADA: 0; errores técnicos de legítimos: 0.
- Asientos obtenidos por bots 244 · liberados (auditoría) 244 · aún bloqueados al final 0.
- Órdenes obtenidas por bots 196 · canceladas (bots / otras): 196 / 0 · cuentas revocadas Postgres (bots / otras): 108 / 0 · Redis: 108.
- Medida independiente de recuperación: sí; seguimientos sin completar: 2.

## Tráfico legítimo (p95 de reservar, bitácora del generador)

| Fase | Durante recuperaciones (n) | p95 durante | Fuera de recuperaciones (n) | p95 fuera |
|---|---|---|---|---|
| normal | 36 | 26.2 ms | 374 | 23.0 ms |
| pico | 258 | 10.0 ms | 1177 | 10.0 ms |

## Colas y descartes (Prometheus)

| Fase | cola_evento_trafico máx | cola_operacion máx | cola_alerta máx | eventos descartados | rechazos cuenta revocada |
|---|---|---|---|---|---|
| normal | 0.0 | 0.0 | 0.0 | 0.0 | 5.2 |
| pico | 0.0 | 0.0 | 0.0 | 0.0 | 29.2 |
