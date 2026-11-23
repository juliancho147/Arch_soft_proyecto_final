# EXP-3 — Seguridad: detectar y recuperarse de un ataque (S-1 y S-2)

Hipótesis, tácticas y criterios: ver [`../../Plan-Experimentos-TAQ.md`](../../Plan-Experimentos-TAQ.md) (sección EXP-3) y los ASR S-1 y S-2 en [`../../ASRs-TAQ.md`](../../ASRs-TAQ.md).

**Estado:** los componentes, el generador de ataques, los verificadores, el tablero y los manifiestos están **desarrollados y probados en local con Redis y PostgreSQL efímeros** (corridas de humo con cargas pequeñas). **Nada se ha desplegado en EKS ni ejecutado a escala del plan.** Ver "Qué falta" al final.

## Tiempos de los ASR usados como umbral

| ASR | Medida de respuesta | Cómo se mide en el experimento |
|---|---|---|
| S-1 detectar | **≤ 100 ms** desde que el evento llega al detector | `taq_deteccion_seconds`: desde que el evento sale de `cola_evento_trafico` hasta que la evidencia queda insertada en `bd_auditoria`. p95 por fase (normal y pico). |
| S-2 recuperarse | **≤ 300 ms** | `taq_recuperacion_seconds`: desde la alerta hasta asientos liberados + órdenes canceladas + cuenta revocada. Además, medida independiente (`medir_recuperacion.py`). |

## Mapeo a la arquitectura del plan

| Elemento del plan | Dónde está |
|---|---|
| `componente_api_gateway` publica cada solicitud | `gateway/EventosTrafico.java` + cambios mínimos en `GatewayController` (solo con `TAQ_DETECCION=on`) |
| `cola_evento_trafico` | lista Redis `cola_evento_trafico` (comando asíncrono de Lettuce, sin esperar; acotada) |
| `componente_deteccion_ataque` | rol `deteccion`: `deteccion/DetectorAtaques.java` (ventanas deslizantes por cuenta y por IP en memoria) |
| `componente_parametrizacion` (reglas antifraude) | `deteccion/Parametros.java` + `ParametrizacionController` (`GET/PUT /parametros`, hash Redis `parametros_antifraude`, releído cada 5 s) |
| `bd_auditoria` | tabla Postgres `auditoria_seguridad` (se crea sola al arrancar) |
| alerta | lista Redis `cola_alerta_ataque` |
| `componente_respuesta_ataque` | rol `respuesta`: `respuesta/RespuestaAtaque.java` |
| `componente_revocacion_acceso` | conjunto Redis `cuentas_revocadas` + tabla `cuenta_revocada`; el gateway lo copia a memoria cada ~1 s y responde 403 `CUENTA_REVOCADA` |
| `componente_restauracion_estado` | endpoint `POST /bloqueo/liberar-comprador` de `bd_bloqueo` apoyado en el **índice en memoria comprador → asientos** (mantenido solo dentro del hilo único) |
| cancelación de órdenes en `bd_reserva` | tabla `orden_cancelada` (ver decisiones) |
| `bd_bloqueo` / `cola_operacion` | la liberación masiva entra por la cola del hilo único, como cualquier otra operación |

## Cómo se activa

Todo está **apagado por defecto**. Con `TAQ_DETECCION=off` (valor por defecto, propiedad `taq.deteccion`) el gateway y `bd_bloqueo` se comportan exactamente como en EXP-1/EXP-2: no existe `EventosTrafico`, el índice no se mantiene, las métricas nuevas no se registran y el generador produce el mismo calendario y la misma bitácora (14 columnas).

| Variable | Rol | Por defecto | Descripción |
|---|---|---|---|
| `TAQ_ROLE` | todos | `gateway` | ahora también `deteccion` y `respuesta` |
| `TAQ_DETECCION` | gateway, bd_bloqueo, deteccion, respuesta | `off` | `on` activa eventos, 403 por cuenta revocada, índice y rechazo de revocados en `bd_bloqueo` |
| `TAQ_EVENTO_COLA_MAX` | gateway | 50000 | si `cola_evento_trafico` supera este tamaño, se descartan eventos y se cuentan |
| `TAQ_EVENTO_VUELO_MAX` | gateway | 5000 | comandos Redis asíncronos sin confirmar permitidos a la vez (otra cota) |
| `TAQ_REVOCADAS_REFRESCO_MS` | gateway | 1000 | refresco de la copia local de `cuentas_revocadas` |
| `TAQ_DETECCION_HILOS` / `TAQ_RESPUESTA_HILOS` | deteccion / respuesta | 4 / 4 | hilos de consumo (BRPOP) |
| `TAQ_AF_VENTANA_S`, `TAQ_AF_UMBRAL_CUENTA`, `TAQ_AF_UMBRAL_IP`, `TAQ_AF_UMBRAL_ASIENTOS` | deteccion | 30 / 3 / 20 / 7 | valores iniciales de las reglas (luego mandan los de Redis) |
| `TAQ_ORACULO_PREFIJO_BOT` | deteccion | `bot-` | **solo instrumentación**: cuentas marcadas que no llevan este prefijo se cuentan en `taq_marcas_falsos_positivos_total` (compradores legítimos marcados) |

## Cómo se ejecuta (EKS)

Todo desde `exp3/aws/scripts/` (los scripts **no se han ejecutado**):

1. `publicar-imagen.sh` — construye y publica **solo** `taq-plataforma:$TAG` (arm64; `TAG=1.3` por defecto). No toca la `1.0` ni la `1.1`. (`publicar-imagen-1.1.sh` se conserva y solo llama al anterior con `TAG=1.1`.)
2. `activar-exp3.sh` — genera los manifiestos y el tablero, aplica `20-deteccion-respuesta.yaml` (pods `deteccion` y `respuesta`), `10-plataforma-exp3.yaml` (`nodo-entrada` y `bd-bloqueo` con la imagen `$TAG` y `TAQ_DETECCION=on`) y el tablero `exp3asr`. El **único punto de cambio de la etiqueta** es la variable `TAG` (por defecto `1.3`; `activar-exp3.sh` la exporta a `generar_exp3.py`): `TAG=1.3 ./activar-exp3.sh`. Los manifiestos `k8s/*.yaml` ya generados siguen con la etiqueta anterior hasta que `activar-exp3.sh` los regenere. Para volver a EXP-1/EXP-2: `activar-exp3.sh volver` (reaplica el manifiesto de EXP-2 con imagen 1.0 y sin la variable, y borra los dos pods nuevos).
3. `04-acceso.sh` de EXP-2 y luego `acceso-exp3.sh` (túneles nuevos: detección `:30091`, respuesta `:30092`; los demás ya existen: gateway `:30080`, bd_bloqueo `:30090`, Postgres `:30432`, Prometheus `:30900`, Grafana `:30300`).
4. `run-exp3.sh <n> <semilla>` — corrida completa del plan (1 min calentamiento + 12 min normal con 30 ataques + 2 min rampa + 10 min pico a 8.000/min con 10 ataques), con los **tres tipos de ataque** repartidos por turnos (`TIPOS_ATAQUE=bot_individual,granja_cuentas,acaparador` por defecto; `TIPOS_ATAQUE=bot_individual` reproduce la corrida anterior). También fija `umbral_asientos=7` en Redis (`UMBRAL_ASIENTOS`), porque el hash `parametros_antifraude` sobrevive entre corridas y con la imagen 1.1 quedó en 9. Humo de ~4 min: `SMOKE=1 run-exp3.sh 0 1`. Hace: reinicio de estado → copia de los Groovy al pod `jmeter` → `medir_recuperacion.py` en segundo plano → JMeter dentro del clúster → copia de resultados → verificador D-3 → `verificar_exp3.py` → evidencia de Grafana. Resultados en `exp3/resultados/corrida-<n>/`.

Se ejecuta 2 veces con semillas distintas (80 ataques en total). Los pods nuevos y los de EXP-2 comparten el nodo `sistema` con `bd-bloqueo`: revisar que quepan (detector 500m–2 CPU, respuesta 250m–1 CPU).

Propiedades del generador (JMeter `-J...`, todas opcionales; sin ellas nada cambia): `ataques_normal`, `ataques_pico`, `bots_por_ataque` (100), `solicitudes_bot_por_min` (10), `duracion_max_ataque_s` (60), `ataque_normal_desde_s` (calentamiento previo de 60 s; `calentamiento_s` incluye esos 60 s + los 720 s de tráfico normal), `ip_simuladas`, y para los tipos de ataque:

| Propiedad | Por defecto | Significado |
|---|---|---|
| `tipos_ataque` | `bot_individual` | lista separada por comas; se reparten por turnos, por fase (normal / pico), en partes casi iguales, con un desfase inicial que depende de la semilla (misma semilla = mismo reparto) |
| `bots_por_ataque`, `solicitudes_bot_por_min` | 100, 10 | `bot_individual`: cuentas por ataque y tasa por cuenta (1 asiento por solicitud) |
| `cuentas_por_granja`, `solicitudes_granja_por_cuenta_min` | 100, 3 | `granja_cuentas`: cuentas detrás de UNA IP y tasa por cuenta (la IP junta ≈ 300/min) |
| `cuentas_acaparadoras`, `solicitudes_acaparador_por_min`, `asientos_por_solicitud_acaparador` | 20, 5, 4 | `acaparador`: cuentas (una IP cada una), una solicitud cada 12 s, grupos de 4 asientos distintos |

Las solicitudes de ataque llevan además `tipoAtacante` en el cuerpo JSON. Cada cuenta de ataque es `bot-A<n>-<i>` (única por ataque y distinta de las `c<n>` legítimas) y cada solicitud lleva asientos que nadie más usa (ni otro ataque ni el tráfico legítimo). `X-Forwarded-For`: IP propia por bot (`203.0.A.i`), una sola IP por granja (`198.51.A.1`) e IP propia por acaparador (`100.64.A.i`). Con ataques la bitácora agrega **al final** las columnas `ip` y `tipo_ataque` (etiqueta declarada; vacía en el tráfico legítimo); `ejecucion.json` agrega `tipos_ataque`, `por_tipo` y el `tipo` de cada ataque. Si un tipo no cabe en los asientos libres, se reduce proporcionalmente el máximo de solicitudes por cuenta (queda en `por_tipo.<tipo>.solicitudes_max_por_cuenta`).

### Prueba rápida en local (sin Kubernetes)

Redis y PostgreSQL en contenedores, un `java -jar taq.jar` por rol (`TAQ_ROLE`, `SERVER_PORT`, `TAQ_REDIS_URL`, `TAQ_DB_URL`, `TAQ_BLOQUEO_URL`…) y JMeter con la propiedades de arriba; `medir_recuperacion.py` y `verificar_exp3.py` aceptan `--deteccion/--respuesta/--bloqueo/--prom` para apuntar a los puertos locales. Así se hicieron las pruebas descritas abajo.

## Tipos de ataque y reglas

**El tipo de atacante viene de una etiqueta, no de un clasificador.** El fin del experimento es medir S-1 (detección) y S-2 (recuperación), no construir un clasificador de atacantes: por eso el generador **declara** el tipo de cada atacante con el campo JSON `tipoAtacante` en el cuerpo de `/api/reservar` (`bot_individual`, `granja_cuentas` o `acaparador`; el tráfico legítimo no lo lleva). El gateway (`EventosTrafico`) lo copia al evento de `cola_evento_trafico`, y el detector lo copia **tal cual** a la evidencia (`bd_auditoria`: columna `tipo_atacante` y `detalle.tipo_atacante`), a la alerta, al log y a las métricas (etiqueta `tipo`). Si el evento no trae la etiqueta (o trae un valor desconocido), se usa `sin_etiqueta`. **El detector no usa la etiqueta para decidir si hay ataque** ni para elegir regla: las reglas son las de siempre y la etiqueta solo permite desglosar S-1, S-2 y las marcas por tipo en la verificación y el tablero.

Los tres tipos son de **reventa** y cada uno lo delata una señal distinta; la verificación comprueba que cada tipo se detecta con la regla esperada:

| Tipo | Cómo ataca (generador) | Señal | Regla esperada |
|---|---|---|---|
| **`bot_individual`** | cada bot: IP fija propia + cuenta propia, ~10 solicitudes/min de 1 asiento distinto (100 bots por ataque) | muchas reservas de una misma cuenta | `cuenta_frecuencia` |
| **`granja_cuentas`** | 100 cuentas detrás de UNA IP, ~3 solicitudes/min por cuenta (≤ 2 en la ventana: ninguna alcanza el umbral por cuenta), ≈ 300/min en la IP | muchas solicitudes desde una misma IP | `ip_frecuencia` (la que cruza el umbral y marca en bloque las cuentas vistas) e `ip_marcada` (cuentas que llegan después) |
| **`acaparador`** | 20 cuentas (una IP cada una), 1 solicitud cada ~12 s (5/min) con 4 asientos distintos cada una | demasiados asientos pedidos por una cuenta en la ventana, a un ritmo bajo | `cuenta_asientos` |

Algoritmo sin cambios respecto a la imagen 1.1 (orden: `cuenta_frecuencia`, `cuenta_asientos`, `ip_marcada`/`ip_frecuencia`; la primera que se cumple marca). Un ataque se define por el **comportamiento del actor**, no por el volumen total. Un comprador legítimo del generador usa una cuenta distinta (`c<n>`), hace 1 reserva (+1 confirmación) y, en los conflictos, 1 solicitud de 1–4 asientos; el generador no hace reintentos.

| Parámetro | Valor | Justificación |
|---|---|---|
| `ventana_s` | 30 | Con 10 reservas/min un bot acumula 5 en la ventana; un comprador legítimo, 1–2. |
| `umbral_cuenta` | **3** reservas de una cuenta en la ventana | Un legítimo no llega (1 reserva; 2 con un reintento). Un bot llega en su 3.ª solicitud, unos 12 s después de empezar (tiempo de la marca, no de la detección: S-1 mide desde que el evento entra al detector). Una cuenta de granja (3/min) tiene a lo sumo 2 en la ventana: el margen de 1 evita que se marque por cuenta. |
| `umbral_asientos` | **7** (antes 9): más de 7 asientos pedidos (acumulados) por una cuenta en la ventana. **Solo cambia el parámetro, no el código.** | Un legítimo pide hasta 4 asientos en 1 solicitud. El acaparador pide 4 por solicitud cada 12 s: con 2 solicitudes suma 8 > 7 y dispara `cuenta_asientos` antes de llegar a 3 solicitudes (`cuenta_frecuencia`). Con 9 no se dispararía con 2 solicitudes y la marcaría la regla de frecuencia. **Limitación:** el conteo es acumulado, no de asientos distintos; un reintento legítimo de los mismos 4 asientos sumaría 8 y se marcaría. El generador no hace reintentos, así que no hay falsos positivos en el experimento, pero un comprador real que reintente sí los tendría. |
| `umbral_ip` | 20 solicitudes de una misma IP en la ventana | Solo se aplica a IP de cliente (`X-Forwarded-For`); detrás de un balanceador la IP remota es la del balanceador y no identifica a nadie. Cada bot o acaparador usa su IP (≈ 5 solicitudes en la ventana); la granja junta ≈ 5 por segundo y cruza 20 en ≈ 4 s. Un comprador legítimo del generador usa una IP por comprador. 0 la desactiva. |

Se pueden cambiar sin reiniciar: `curl -X PUT -H 'Content-Type: application/json' -d '{"umbral_cuenta":4}' http://localhost:30091/parametros` (cada réplica del detector los relee de Redis en ≤ 5 s). **La tasa de falsos positivos solo está validada contra el tráfico legítimo del generador**, no contra compradores reales; el ASR S-1 declara que no la valida.

### Métricas por tipo

- `taq_ataques_detectados_total{regla, tipo}` (se conserva `regla`; `tipo` es la etiqueta declarada por el generador).
- `taq_deteccion_seconds{tipo}` y `taq_recuperacion_seconds{tipo}`: un histograma por tipo (`bot_individual`, `granja_cuentas`, `acaparador`, y `sin_etiqueta` si el evento no trae etiqueta o trae una desconocida). Las consultas existentes con `sum(rate(..._bucket[..])) by (le)` siguen valiendo (suman todos los tipos); para un tipo basta `..._bucket{tipo="acaparador"}`. Cardinalidad: 4 series por cubeta, sin crecer con el número de cuentas.
- `TAQ_DETECCION=off` no cambia: no se registra nada de esto.

### Fuera de alcance (limitaciones)

- **Rotación de dispositivo**: no hay contador por dispositivo (huella del cliente); un atacante que rote de dispositivo/IP con una cuenta por solicitud no se distingue de compradores distintos.
- **Inundación DoS**: es un problema de disponibilidad (límites de tasa en el borde), no de reventa; el detector no la trata y el gateway descarta eventos si `cola_evento_trafico` se llena.
- **"Bajo y lento"**: un atacante que se mantenga bajo los umbrales (menos de 3 reservas y 8 asientos distintos por cuenta y 20 solicitudes por IP en 30 s) no se detecta con ventanas de 30 s; exigiría ventanas largas o acumulados por cuenta/día.
- **No hay clasificador**: si un atacante real no declara etiqueta, queda como `sin_etiqueta`. Además, la regla que lo marca puede no coincidir con la "esperada" si el atacante cambia sus tasas (p. ej. una granja con más de 2 solicitudes por cuenta en 30 s se marcaría por `cuenta_frecuencia`); los umbrales evitan solapes solo con las tasas del plan.
- El conteo de asientos de `cuenta_asientos` es acumulado (reintentos con los mismos asientos suman).

### Evolución del algoritmo de marca y recuperación (v1 -> v2)

Mejora de **ejecución** (orden y lotes de las escrituras). No cambian las reglas, sus umbrales, su orden ni el significado de la etiqueta `tipoAtacante`.

| | v1 (imagen 1.2) | v2 (imagen 1.3) |
|---|---|---|
| Marca de una IP (`ip_frecuencia`) | secuencial en un hilo: por cada cuenta SADD en Redis, INSERT de la evidencia, contadores, histograma, LPUSH de la alerta y `log.info` | (a) SADD de todas las cuentas en un pipeline (un viaje); (b) UN INSERT multifila con la evidencia de todas; (c) **solo después** de escrita la evidencia: métricas, un único LPUSH con todas las alertas y una línea de log por lote |
| Recuperación | cada alerta por separado: un POST a `bd_bloqueo` (una espera en la cola del hilo único), un SADD, una transacción con INSERT por fila | el hilo de respuesta drena hasta 200 alertas por ciclo (`RPOP` con cuenta; un solo hilo espera y drena a la vez para que la ráfaga caiga entera en un lote): UN SADD múltiple, UN `POST /bloqueo/liberar-compradores` (una sola operación del hilo único; `liberar-comprador` se conserva) y inserciones multifila en una transacción (cuentas revocadas, órdenes canceladas) y, después, la evidencia |
| Por qué | con ~10 ms por cuenta (viaje a Redis, a Postgres y a `log`), las cuentas finales de una granja de 100 pasaban de 100 ms de detección y de 300 ms de recuperación | el costo deja de crecer con el número de cuentas del lote |

Las definiciones de las métricas no cambian: `taq_deteccion_seconds{tipo}` mide, por cuenta, desde que el evento ENTRA al detector hasta que su evidencia queda escrita en `bd_auditoria` (el lote comparte esa duración); `taq_recuperacion_seconds{tipo}` mide, por cuenta, desde SU alerta hasta liberación + cancelación + revocación; se conservan `taq_recuperacion_etapa_seconds` (cada etapa se registra por cuenta con la duración del lote), la evidencia de recuperación posterior (4 filas por cuenta, ahora con campo `lote`) y las filas de `ATAQUE_DETECTADO` (con `lote` en `detalle` cuando son varias). Un ataque de una sola cuenta (bot individual, acaparador, `ip_marcada`) usa el mismo código con una lista de 1. Riesgo conocido: si falla el lote (p. ej. `bd_bloqueo` caído) las alertas del lote se reencolan juntas y, como antes, una segunda pasada ya no ve los asientos liberados en la primera. `RPOP` con cuenta exige Redis ≥ 6.2; con uno anterior el drenado falla y se procesa de a una alerta.

**Línea base v1 en EKS** (`resultados/ensayo-humo-4-algoritmo-v1/`, granja de 30 cuentas): p95 de detección 182 ms (auditoría) / 190 ms (Prometheus) y p95 de recuperación 234 ms (medida independiente) / 167 ms (interna). Las 20 marcas de `ip_frecuencia` tardaron 4, 17, 42, … 210 ms: crecían ~10 ms por cuenta.

**Comparación local v1 vs v2** (Redis/PostgreSQL efímeros en Docker, procesos `java -jar` por rol, JMeter mínimo; 6 ataques: 2 granjas de **100 cuentas**, 2 bots de 10, 2 acaparadores de 5; misma semilla; el medidor independiente corre en la misma máquina). Aquí el RTT a Redis/Postgres es ≈ 0 y la máquina estaba cargada, así que los valores absolutos son mucho menores que en EKS; lo que importa es la forma:

| Prueba local | Detección granja (p95 / máx), auditoría | Recuperación granja interna (p95 / máx) | Recuperación independiente, ataque de granja (p95 / máx) |
|---|---|---|---|
| A. umbral_ip=20 (20 cuentas por lote de `ip_frecuencia`; las otras 80, `ip_marcada` de a una): v1 | marcas de `ip_frecuencia`: 56 / 59 ms (los 200 marcas: casi todas ≤ 10 ms) | 84 / 90 ms | 43 / 50 ms y 142 / 150 ms |
| A. v2 | `ip_frecuencia`: 3 / 3 ms | 45 / 45 ms | 39 / 49 ms y 132 / 132 ms |
| B. umbral_ip=100 (lote de ~100 cuentas por ataque, solo para esta prueba): v1 | **116 / 126 ms** (> 100 ms) | 61 / 68 ms | 97 / 100 ms y 83 / 85 ms |
| B. v2 | **15 / 15 ms** (log: 21 y 13 ms con el INSERT) | 28 / 28 ms | 64 / 64 ms y 60 / 60 ms |

Histograma de Prometheus del tipo `granja_cuentas`, prueba B (200 marcas): detección v1 ≤ 50 ms 78, ≤ 100 ms 174, ≤ 200 ms 200; v2 todas ≤ 50 ms. Recuperación v1 ≤ 50 ms 144, todas ≤ 100 ms; v2 todas ≤ 50 ms. Bot individual y acaparador no cambian (detección ≈ 1-2 ms, recuperación interna ≈ 10-15 ms en ambas versiones). En las pruebas del tipo bot/acaparador y en las de granja no hubo compradores legítimos marcados. La "medida independiente" del medidor sube con el número de seguimientos abiertos (cada ciclo consulta todas las cuentas pendientes), por lo que con 100 cuentas sobrestima. La prueba B usa `umbral_ip=100` solo para forzar un lote de ~100 y comprobar el peor caso de la recuperación en bloque; con el umbral del plan (20) cada marca en bloque abarca ~20 cuentas.

## Decisiones y desviaciones del plan (revisar)

1. **Cancelación de órdenes.** `reserva_log` es un registro de solo anexar, sin unicidad ni índice por comprador, y se llena de forma asíncrona. En vez de actualizarla (escaneo completo y condiciones de carrera con la persistencia), la cancelación se anota en la tabla nueva `orden_cancelada` (una fila por solicitud retenida que se liberó, con sus asientos). El conjunto de órdenes sale de la propia respuesta de `bd_bloqueo` (la fuente de verdad de lo que estaba retenido). Si se prefiere marcarlo en `reserva_log`, hay que agregarle un índice por comprador.
2. **Qué cuenta dentro de los 300 ms de S-2.** Alerta → revocación en Redis → liberación en `bd_bloqueo` (por su hilo único) → transacción en Postgres con `cuenta_revocada` y `orden_cancelada`. Queda **fuera** del tiempo, y se escribe después, la evidencia de recuperación en `bd_auditoria` (4 filas por cuenta), como "limpieza definitiva asíncrona" del ASR. El gateway tarda hasta ~1 s en dejar de aceptar la cuenta (copia local), pero `bd_bloqueo` rechaza desde el instante de la liberación las reservas de esa cuenta que ya iban en la cola (`CUENTA_REVOCADA`), así que no se retienen asientos nuevos.
3. **Revocar en bd_bloqueo.** `POST /bloqueo/liberar-comprador` con `revocar:true` añade al comprador a un conjunto en memoria del hilo único; es un añadido al diseño del plan, necesario para que una solicitud en vuelo no vuelva a bloquear asientos justo después de liberarlos.
4. **Reloj de S-2.** Se mide con el reloj de los pods (alerta en el detector, fin en el pod de respuesta); depende de que los nodos estén sincronizados por NTP (en EKS, Amazon Time Sync). `medir_recuperacion.py` usa también solo relojes de pods (no el de la máquina del usuario).
5. **Eventos del gateway.** Se publican tanto `reservar` como `confirmar`. La regla por cuenta cuenta solo `reservar`. Un 403 `CUENTA_REVOCADA` no se registra en `taq_reservar_seconds` (tiene su contador `taq_rechazos_cuenta_revocada_total`), así que no altera el histograma de EXP-1/2. Las reservas de los bots **sí** están en `taq_reservar_seconds` (son tráfico real al gateway): el p95 de Grafana mezcla ~12 % de bots; el p95 exacto del tráfico legítimo sale de la bitácora (`verificar_exp3.py`).
6. **IP simulada del tráfico legítimo.** Con ataques activos, el generador envía también `X-Forwarded-For` en el tráfico legítimo (una IP `10.x.y.z` por comprador, derivada de `c<n>`); si no, todo el tráfico legítimo llegaría con la IP del pod JMeter. Solo ocurre si `ataques_*` > 0 o `ip_simuladas=true`.
7. **Asientos de los bots.** Salen de los asientos que el tráfico normal y los conflictos no usan (los "frescos" sobrantes más los que están por encima del último bloque de conflictos), sin repetir ninguno (repetirlos haría creer al verificador D-3 que hay doble reserva). Con 40 ataques × 100 bots, el tope por bot (`duracion_max_ataque_s` × tasa) se reduce si no hay asientos suficientes; el valor efectivo queda en `ejecucion.json → exp3.solicitudes_max_por_bot`.
8. **Bitácora.** Con ataques se agregan al **final** las columnas `ip` y `tipo_ataque`. Los bots se registran con `tipo=ATAQUE_BOT`, `grupo=<id del ataque>` (`A1`, `A2`…), `comprador=bot-A<n>-<i>`. Los lectores existentes (`Verificador`, `recolectar*.py`) leen por posición o por nombre de columna y se probaron con ese archivo.
9. **Estado de las marcas.** El detector es en memoria: si se reinicia, olvida ventanas y marcas locales (el conjunto Redis `cuentas_marcadas` evita doble marca entre réplicas, y `reiniciar-estado-exp3.sh` lo borra entre corridas). Con varias réplicas del detector cada una vería solo parte de las solicitudes de una cuenta; el experimento usa una réplica (los eventos de una cuenta no se reparten por clave).
10. **Marca masiva por IP.** Si una IP supera el umbral, se marcan en secuencia todas las cuentas vistas en su ventana desde un mismo hilo; con cientos de cuentas por IP los últimos tardarían más de 100 ms. Con la granja de cuentas (100 cuentas tras una IP) ocurre: (v2: en un solo lote) la marca masiva afecta solo a las ≈ 20 cuentas vistas en la ventana al cruzar el umbral (≈ 4 s tras empezar); las demás se marcan una a una con `ip_marcada` al llegar su primera solicitud. Vigilar el p95 de detección de `granja_cuentas`.
11. **Medición independiente.** Consulta HTTP al estado real (hilo único de `bd_bloqueo` + Redis + Postgres vía el pod `respuesta`), por lo que añade una pequeña carga de lectura durante la recuperación y sus consultas a `bd_bloqueo` esperan en la misma cola. La cota es superior (la consulta llega unos ms después del cambio de estado).

## Verificación

`verificar_exp3.py <carpeta>` escribe `verificacion.md/json`. Criterios: todos los ataques y todos los bots marcados; **todos los ataques de cada tipo detectados**; 0 compradores legítimos marcados o revocados; 0 asientos de bots bloqueados al final; asientos liberados = asientos obtenidos por los bots (bitácora: el acaparador obtiene 4 por solicitud); órdenes canceladas = solicitudes de bots que lograron reservar; cuentas revocadas = bots; p95 de detección ≤ 100 ms y p95 de recuperación ≤ 300 ms por fase (normal y pico; Prometheus + auditoría + medida independiente). También informa: solicitudes fraudulentas que pasaron antes de la marca, p95 del tráfico legítimo dentro y fuera de las ventanas de recuperación (bitácora), y profundidad máxima de `cola_evento_trafico`, `cola_operacion` y `cola_alerta` por fase. Sale con código 0 solo si todo cumple. El D-3 de EXP-1 se corre sobre la misma bitácora (los bots no deben producir dobles reservas).

Sección **"Tipos de ataque"** (también en `verificacion.json → tipos_de_ataque`): tabla de **consistencia** por tipo etiquetado: ataques inyectados y detectados, cuentas marcadas, regla que disparó cada marca, si la etiqueta guardada en la auditoría coincide con la declarada, solicitudes fraudulentas antes de la marca, p95 de detección (auditoría y Prometheus por etiqueta `tipo`) y p95 de recuperación (medida independiente si hay datos, interna y Prometheus). Criterios: "todos los ataques de cada tipo detectados" y 0 legítimos marcados. No hay matriz de confusión: el tipo no se infiere.

## Tablero

`aws/dashboards/gen-dashboard-exp3.py` → `exp3-dashboard.yaml` (ConfigMap, `monitoring`, etiqueta `grafana_dashboard: "1"`, uid `exp3asr`) y `exp3-dashboard-local.yaml` (mismo contenido; no usa métricas de Kubernetes). Solo S-1 y S-2: p95 de detección vs 100 ms, p95 de recuperación vs 300 ms (verde/rojo), % dentro del límite, cuentas marcadas vs bots inyectados (`BOTS_ESPERADOS`), cola de eventos y descartes, etapas de la recuperación, cola de operaciones durante la liberación masiva, p95 de reservar vs 250 ms y compradores legítimos marcados. Sin paneles de CPU ni memoria. No se ha cargado en ningún Grafana.

## Qué falta

- Construir y publicar la imagen `1.3` (`publicar-imagen.sh`; `TAG=1.3` por defecto), activarla (`activar-exp3.sh`) y correr `run-exp3.sh` en EKS (humo primero, luego 2 corridas con semillas distintas). La `1.3` se construyó solo en local (`taq/plataforma:1.3`), no se ha publicado. SMOKE=1 usa ya 100 cuentas por granja (tamaño del plan).
- Los tipos de ataque solo se probaron en local con cargas mínimas: falta ver a escala del plan la marca masiva de la granja, el p95 de detección por tipo y los límites de asientos libres con 40 ataques de tres tipos.
- Validar a escala: la detección y la recuperación en el pico de 8.000/min, con la cola real de `bd_bloqueo`; el rendimiento del detector (4 hilos, un INSERT por marca) con 100 marcas casi simultáneas; la ocupación del nodo `sistema`.
- Comprobar el PodMonitor con los dos pods nuevos y las consultas del tablero contra el Prometheus real (las consultas de `verificar_exp3.py` se probaron contra un Prometheus local, el tablero no).
- Confirmar con medidas reales que `EXP-1/EXP-2` no cambian con la imagen 1.3 y `TAQ_DETECCION=off` (solo se comprobó que el comportamiento funcional, las métricas expuestas y la bitácora son los mismos).
