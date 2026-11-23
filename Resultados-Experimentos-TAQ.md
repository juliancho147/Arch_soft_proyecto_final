# Resultados de los experimentos — TAQ

Resumen de la última ejecución válida de cada experimento: qué se midió, contra qué meta y si cumplió.

## 1. Veredicto general

| ASR | Meta | Valor medido | Margen | Experimento | Veredicto |
|---|---|---|---|---|---|
| **D-3** Prevenir la doble reserva | 0 asientos con más de una reserva | 0 dobles · 0 bloqueos parciales (EXP-1 y EXP-2) | Sin margen: la meta es exacta | EXP-1 y EXP-2 | ✅ Cumple |
| **L-1** Confirmar una reserva | p95 ≤ 150 ms | 7,3 ms en la última ejecución (captura); 4,9 a 7,8 ms en las 3 corridas del lote oficial | ≈ 20 veces por debajo | EXP-1 | ✅ Cumple |
| **E-1** Sostener la preventa | p95 < 250 ms, 8.000/min | 7,3 ms en el pico (hasta 23.854 solicitudes/min en la meseta), 0 rechazos | ≈ 34 veces por debajo | EXP-2 | ✅ Cumple |
| **S-1** Detectar un ataque | Detección ≤ 100 ms | p95 = 4,8 ms (resumen del panel; 4,2 ms en la ventana visible de Grafana) · 100 % ≤ 100 ms | ≈ 20 veces por debajo | EXP-3 | ✅ Cumple |
| **S-2** Recuperarse de un ataque | Recuperación ≤ 300 ms | p95 = 14,5 ms · 100 % ≤ 300 ms | ≈ 20 veces por debajo | EXP-3 | ✅ Cumple |

Los cuatro ASRs priorizados y S-2 cumplen. Hay tres matices que conviene decir al presentar:

- **EXP-2 no corrió el perfil planeado.** Corrió 10 min en tramos (400 → 8.000/min en 30 s, hasta 20.000/min), no 15 min sostenidos a 8.000/min. Las cifras de carga superan el pico del ASR, pero la duración del pico es menor.
- **EXP-3 no se ejecutó con el plan original** (30 + 10 ataques con tráfico de fondo). La última ejecución fue una corrida desde el panel de 10 min, con 15 ataques.
- **Latencias muy por debajo de la meta.** Las medidas corren en un entorno controlado, con pasarelas simuladas, y todas son varios órdenes de magnitud menores que el límite. El resultado valida el diseño, no el rendimiento en producción.

---

## 2. EXP-1 · Reserva de asientos en operación normal (L-1 y D-3)

**Veredicto: ✅ Cumple L-1, D-3 y el vencimiento de bloqueos a los 8 min.**

### Contexto de la ejecución

| Dato | Valor |
|---|---|
| Entorno | Kubernetes local (kind, 1 nodo) en un Apple M5 de 10 núcleos y 16 GB; JMeter, Prometheus y Grafana comparten la misma máquina |
| Carga | 400 reservas/min, llegadas aleatorias, 70 % confirma y 30 % abandona, conflictos inyectados con probabilidad 1/20 |
| Réplicas | 1 por componente (sin autoescalado) |
| Lote oficial | 3 corridas válidas (semillas 1, 2 y 3), 60 s de calentamiento + 720 s de tráfico |
| Última ejecución (capturas de Grafana) | 22-nov-2026, aprox. 13:59 a 14:10, tablero `exp1asr` |

### Mediciones del lote oficial (3 corridas)

| Corrida | Llegadas | Conflictos | p50 gw (ms) | **p95 gw (ms)** | p99 gw (ms) | p95 cliente (ms) | % ≤ 150 ms | Atraso del generador p95 |
|---|---|---|---|---|---|---|---|---|
| 1 | 5.189 | 248 | 2,7 | **7,8** | 15,8 | 12,0 | 100 % | 3 ms |
| 2 | 5.237 | 253 | 2,6 | **4,9** | 9,4 | 8,0 | 100 % | 2 ms |
| 3 | 5.352 | 247 | 2,6 | **4,9** | 9,8 | 8,0 | 100 % | 2 ms |

Promedio del p95 del gateway: 5,9 ms; peor: 7,8 ms. La diferencia con lo que ve el cliente es de 3,4 ms en promedio.

| Corrida | Dobles reservas | Bloqueos parciales | Conflictos con resultado esperado | Liberación real p50 / máx | Errores técnicos |
|---|---|---|---|---|---|
| 1 | 0 | 0 | 248 de 248 | 480,5 s / 481,0 s | 0 |
| 2 | 0 | 0 | 253 de 253 | 480,5 s / 481,0 s | 0 |
| 3 | 0 | 0 | 247 de 247 | 480,5 s / 481,0 s | 0 |

### Lo que muestran las capturas de la última ejecución

| Dato visible en Grafana | Valor |
|---|---|
| p95 de reservar (ventana de 5 min) | **7,332 ms** (límite 150 ms), constante a lo largo de toda la ventana |
| Solicitudes recibidas en el rango | ≈ 3.000 |
| Solicitudes simultáneas a una misma silla | Ráfagas de 3 a 20 solicitudes por instante |
| Solicitudes en conflicto | Aprobadas: una pequeña fracción por ráfaga (una por silla); no aprobadas: el resto (`NO_DISPONIBLE`) |
| Sillas con más rechazos | 106 K (19), 108 K (18), 121 K (18), 114 K (17), 128 K (17), 105 K (15) |
| Bloqueos activos | Suben de ≈ 700 a ≈ 1.150 y bajan a ≈ 300 al final de la ventana |
| Liberados por vencimiento (acumulado) | Empiezan hacia las 14:03 (≈ 8 min después del inicio) y llegan a ≈ 960 hacia las 14:10 |

### Comportamiento observado

- Con una sola réplica, el p95 queda 20 veces por debajo del límite, y casi todas las reservas responden en menos de 15 ms.
- En cada ráfaga de conflicto solo una solicitud por silla fue aprobada; las demás recibieron `NO_DISPONIBLE`.
- Los bloqueos abandonados no se liberan antes de los 8 min: la curva de liberados arranca en el instante esperado y la liberación real medida fue de 480,5 s (p50).
- El hilo único de `bd_bloqueo` casi no se ocupa (ocupación promedio 0,0 %, máximo 0,1 %; ≈ 16 operaciones/s), la caché acierta el 99,9 % y las colas no se llenan (máx. 0).

### Hallazgos y desviaciones

- **El conteo exacto de dobles reservas no sale de las capturas.** Las capturas muestran aprobadas contra no aprobadas, pero "0 asientos con más de una reserva" proviene de la verificación del lote oficial (`verificacion.md`), no de la imagen.
- **No pude identificar cuál es su "última corrida" de EXP-1.** Los dos archivos de imagen son de la ejecución del 22-nov (≈ 13:59 a 14:10), con una ventana parcial de 5 min. Si usted tiene los números finales de esa ejecución, reemplácelos en la tabla anterior.
- En una corrida de prueba (`corrida-1-dashboard`, 19-nov) el p95 fue 8,4 ms con 58 errores técnicos de 8.934 solicitudes; no es parte del lote oficial.

### Qué no valida

La competencia entre réplicas (la cubre EXP-2), la latencia que percibe el comprador con su red y el comportamiento bajo fallas. Las cifras incluyen la competencia por recursos de una máquina compartida.

---

## 3. EXP-2 · Escalabilidad de reservas en el pico (E-1 y D-3)

**Veredicto: ✅ Cumple E-1 y D-3.**

### Contexto de la ejecución

| Dato | Valor |
|---|---|
| Ejecución | `corrida-1`, 22-nov-2026, 15:04 a 15:14 (hora local) |
| Entorno | AWS EKS, autoescalado de pods con mínimo 1 y máximo 8 réplicas por pod y objetivo de CPU 60 % |
| Perfil de carga | 400 → 8.000/min en 30 s, 8.000/min hasta el min 2, ascenso a 20.000/min hasta el min 6 y meseta hasta el min 10 |
| Volumen | 109.190 llegadas normales, 5.492 conflictos, 174.990 solicitudes de reservar, 175 K solicitudes en el rango |
| Validez | ✅ Válida: atraso del generador p95 = 2 ms |

### Mediciones de E-1 (límite p95 < 250 ms)

| Medida | Valor |
|---|---|
| **p95 en el pico (con arranque de réplicas)** | **7,3 ms** |
| p95 del último minuto (captura de Grafana) | 4,801 ms |
| % de reservas ≤ 200 ms / ≤ 300 ms en el pico | 100,0 % / 100,0 % |
| p95 que ve el generador de carga | 12 ms |
| Solicitudes en el pico | 166.266 (≈ 17.502/min) |
| Rechazos por cola llena | 0 |
| Errores técnicos en el pico | 0 |

| Fase | Solicitudes/min | p95 | Errores | Réplicas máx. (entrada / pasarela / reserva) |
|---|---|---|---|---|
| pico 8k (30 a 120 s) | 7.860 | 9,6 ms | 0 | 2 / 1 / 2 |
| ascenso (120 a 360 s) | 14.827 | 6,5 ms | 0 | 2 / 2 / 2 |
| meseta 20k (360 a 600 s) | 23.854 | 7,2 ms | 0 | 2 / 2 / 2 |

### Equilibrio del autoescalado

| Pod | Máximo | Final | Último cambio |
|---|---|---|---|
| nodo-entrada | 2 | 2 | 75 s |
| nodo-reserva | 2 | 2 | 75 s |
| nodo-pasarela | 2 | 1 | 615 s |

El sistema se equilibró con **2 réplicas por pod, lejos del máximo de 8**. En la captura, el uso de CPU por pod se mantiene por debajo del objetivo de 60 % durante casi todo el pico (con picos puntuales al inicio, cerca de 95 %, mientras escalaba).

### Hilo único de `bd_bloqueo`

| Medida | Valor |
|---|---|
| Operaciones por segundo (máx. / prom.) | 602,4 / 407,2 |
| Ocupación máxima | 0,9 % |
| Cola máxima | 1,0 |
| Pico requerido por el ASR | ≈ 133 operaciones/s |

El hilo único atiende más de cuatro veces la carga requerida con menos de 1 % de ocupación: **no es el cuello de botella**.

### Mediciones de D-3

| Comprobación | Esperado | Obtenido |
|---|---|---|
| Asientos con más de una reserva (auditoría, bitácora y `reserva_log`) | 0 | 0 |
| Asientos bloqueados dos veces dentro del TTL | 0 | 0 |
| Bloqueos parciales (todo o nada roto) | 0 | 0 |
| Conflictos con el resultado esperado | 5.492 de 5.492 | 5.492 de 5.492 |
| Vendidos en `reserva_log` = vendidos en `bd_bloqueo` | iguales | 76.567 = 76.567 |
| Revisión a los 4 min rechazada | todas | 19.611 de 19.611 |
| Revisión pasados los 8 min exitosa | todas | 4.944 de 4.944 |
| Tiempo real bloqueo → liberación (mín / p50 / máx) | ≈ 480 s | 480,0 / 480,5 / 481,0 s |

Por tipo de conflicto: mismo asiento 1.896, grupos cruzados 1.808, asiento vendido 1.788; todos con el resultado esperado.

### Hallazgos y desviaciones

- **Perfil distinto al plan.** El pico se sostuvo 9 min (30 a 600 s), no 15, y subió hasta 20.000/min. Se acordó así tras el intento local fallido por memoria.
- **p95 "tras el equilibrio" = n/d.** Las réplicas se estabilizaron en 615 s, ya fuera de la ventana de 600 s, así que no hubo ventana posterior para medirlo.
- **11 errores técnicos en toda la corrida** (de 174.990 solicitudes), ninguno dentro de la ventana del pico.
- **Una sola ejecución.** El plan pedía 2 con semillas distintas; para esta evidencia se tiene `corrida-1`. Los intentos locales anteriores quedaron descartados (OOMKilled, `descartadas/`).

### Qué no valida

Cargas por encima de las ejecutadas, varios eventos de alta demanda a la vez, el comportamiento bajo fallas (D-1 y D-2), la latencia con la red del comprador, y el escalado del bloqueo atómico (su techo es el del hilo único; medido en ≈ 602 operaciones/s).

---

## 4. EXP-3 · Seguridad: detectar y recuperarse de un ataque (S-1 y S-2)

**Veredicto: ✅ Cumple S-1 y S-2.**

### Contexto de la ejecución

| Dato | Valor |
|---|---|
| Ejecución | Corrida desde el panel de control, 22-nov-2026, 17:24 a 17:34 (hora local) |
| Duración | 10 min 0 s |
| Ataques | 15, en momentos aleatorios, 940 cuentas atacantes inyectadas |
| Tipos | Bot individual (4 ataques), granja de cuentas (4) y acaparador de asientos (7) |
| Entorno | Prometheus y Grafana con la imagen 1.1 de la plataforma; no verifiqué en los archivos si corrió en kind o en AWS EKS (confírmelo) |

### Mediciones de S-1 y S-2

| Medida | Límite | Valor | Veredicto |
|---|---|---|---|
| **S-1** p95 de detección | ≤ 100 ms | **4,8 ms** (resumen); 4,2 ms (ventana visible de Grafana) | ✅ |
| % de detecciones ≤ 100 ms | — | 100,0 % | ✅ |
| **S-2** p95 de recuperación | ≤ 300 ms | **14,5 ms** | ✅ |
| % de recuperaciones ≤ 300 ms | — | 100,0 % | ✅ |
| Compradores legítimos marcados | 0 | 0 | ✅ |
| Solicitudes fraudulentas que pasaron antes de la marca (promedio por cuenta) | dato adicional | 3,6 a 3,7 | — |

### Recuperación

| Dato | Valor |
|---|---|
| Cuentas atacantes marcadas | 940 de 940 |
| Cuentas revocadas | 940 |
| Asientos liberados | 2.720 |
| Órdenes canceladas | 1.880 |

### Por tipo de ataque

| Tipo | Ataques | Cuentas inyectadas / marcadas | p95 detección | p95 recuperación | Regla que disparó |
|---|---|---|---|---|---|
| Bot individual | 4 | 400 / 400 | 3,7 ms | 11,6 ms | `cuenta_frecuencia` (400) |
| Granja de cuentas | 4 | 400 / 400 | 7,0 ms | 20,0 ms | `ip_frecuencia` (80) e `ip_marcada` (320) |
| Acaparador de asientos | 7 | 140 / 140 | 5,0 ms | 15,0 ms | `cuenta_asientos` (140) |

Entre un cuarto y la mitad de las solicitudes de cada ataque se rechazaron por cuenta revocada (bot individual: 300 OK y 100 rechazadas de 400; granja: 100 y 100 de 200; acaparador: 40 y 20 de 60). Es lo esperado: lo que pasa antes de la marca se aprueba y lo que llega después se rechaza.

### Comparación con la corrida de verificación completa (`corrida-0`, 17:14)

Esta corrida corta (5 ataques, 248 bots, pico de 2.000/min) sí pasó la verificación completa cruzando bitácora, auditoría y estado final:

| Criterio | Resultado |
|---|---|
| Ataques detectados / bots marcados | 5 de 5 / 248 de 248 |
| Compradores y cuentas legítimas marcadas o revocadas | 0 |
| Asientos de bots retenidos al final | 0 (384 obtenidos = 384 liberados) |
| Órdenes canceladas y cuentas revocadas | 336 = 336 · 248 = 248 |
| S-1 p95 (Prometheus), normal / pico | 13,7 ms / 4,6 ms |
| S-2 p95 (medida independiente), normal / pico | 176,0 ms / 25,0 ms |

En esta corrida, la recuperación de la granja de cuentas llegó a 176 ms en fase normal, más cerca del límite que en la corrida del panel (20,0 ms).

### Hallazgos y desviaciones

- **No es el plan original.** El plan pedía 30 ataques en tráfico normal y 10 en el pico, en 2 ejecuciones (80 ataques). La última ejecución son 15 ataques, de tamaño 20 a 100 cuentas, y la verificación completa existe solo para la corrida corta (`corrida-0`), no para la del panel.
- **El tipo de ataque lo declara el generador** con la etiqueta `tipoAtacante`; el detector no clasifica. Lo que se comprueba es que cada ataque disparó la regla esperada.
- **La línea base "antes".** El algoritmo original de marca en bloque (v1) incumplía S-1 con la granja de 30 cuentas (p95 de detección 182 ms) y rozaba el límite de S-2 (234 ms). El algoritmo v2, con evidencia y recuperación en lote, es el que produce estos resultados.
- **Dos cifras para S-1** (4,8 y 4,2 ms): el resumen del panel y la ventana visible del tablero abarcan rangos distintos; ambas cumplen por un margen amplio.
- **Prueba de humo descartada de evidencia:** una de ellas no detectó la granja porque Kubernetes ocultaba el encabezado `X-Forwarded-For`.

### Qué no valida

El bloqueo del ataque como tal (solo se mide detectar y recuperarse), los ataques de bajo volumen que no superen el umbral, la tasa de falsos positivos más allá de los 0 observados, las boletas ya revendidas fuera de la plataforma y la limpieza definitiva de los registros (que ocurre después de los 300 ms).

---

## 5. Evidencias

| Experimento | Dónde está |
|---|---|
| EXP-1 | `experimentos/exp1/resultados/` (`resumen-exp1.md`, `corrida-1..3`, `entorno.md`) · `evidencias/Exp1/` (2 capturas y 1 video) |
| EXP-2 | `experimentos/exp2/resultados/corrida-1/` (`resumen.md`, `metricas.md`, `verificacion.md`, `bitacora.csv`, `prometheus/`, `tablero-grafana.json`) · `evidencias/Exp2/` (captura y video) |
| EXP-3 | `experimentos/exp3/resultados/corrida-panel-20261122-1827/` y `corrida-0/` · `evidencias/Exp3/` (captura y `exp3-resumen.md`) |
| Descartes | `descartadas/` y `ensayo-humo*` se conservan en disco y no se usan como evidencia |
