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
| `TAQ_AF_VENTANA_S`, `TAQ_AF_UMBRAL_CUENTA`, `TAQ_AF_UMBRAL_IP`, `TAQ_AF_UMBRAL_ASIENTOS` | deteccion | 30 / 3 / 20 / 9 | valores iniciales de las reglas (luego mandan los de Redis) |
| `TAQ_ORACULO_PREFIJO_BOT` | deteccion | `bot-` | **solo instrumentación**: cuentas marcadas que no llevan este prefijo se cuentan en `taq_marcas_falsos_positivos_total` (compradores legítimos marcados) |

## Cómo se ejecuta (EKS)

Todo desde `exp3/aws/scripts/` (los scripts **no se han ejecutado**):

1. `publicar-imagen-1.1.sh` — construye y publica **solo** `taq-plataforma:1.1` (arm64). No toca la `1.0`.
2. `activar-exp3.sh` — genera los manifiestos y el tablero, aplica `20-deteccion-respuesta.yaml` (pods `deteccion` y `respuesta`), `10-plataforma-exp3.yaml` (`nodo-entrada` y `bd-bloqueo` con imagen 1.1 y `TAQ_DETECCION=on`) y el tablero `exp3asr`. Para volver a EXP-1/EXP-2: `activar-exp3.sh volver` (reaplica el manifiesto de EXP-2 con imagen 1.0 y sin la variable, y borra los dos pods nuevos).
3. `04-acceso.sh` de EXP-2 y luego `acceso-exp3.sh` (túneles nuevos: detección `:30091`, respuesta `:30092`; los demás ya existen: gateway `:30080`, bd_bloqueo `:30090`, Postgres `:30432`, Prometheus `:30900`, Grafana `:30300`).
4. `run-exp3.sh <n> <semilla>` — corrida completa del plan (1 min calentamiento + 12 min normal con 30 ataques + 2 min rampa + 10 min pico a 8.000/min con 10 ataques). Humo de ~4 min: `SMOKE=1 run-exp3.sh 0 1`. Hace: reinicio de estado → copia de los Groovy al pod `jmeter` → `medir_recuperacion.py` en segundo plano → JMeter dentro del clúster → copia de resultados → verificador D-3 → `verificar_exp3.py` → evidencia de Grafana. Resultados en `exp3/resultados/corrida-<n>/`.

Se ejecuta 2 veces con semillas distintas (80 ataques en total). Los pods nuevos y los de EXP-2 comparten el nodo `sistema` con `bd-bloqueo`: revisar que quepan (detector 500m–2 CPU, respuesta 250m–1 CPU).

Propiedades nuevas del generador (JMeter `-J...`, todas opcionales; sin ellas nada cambia): `ataques_normal`, `ataques_pico`, `bots_por_ataque` (100), `solicitudes_bot_por_min` (10), `duracion_max_ataque_s` (60), `ataque_normal_desde_s` (calentamiento previo de 60 s; `calentamiento_s` incluye esos 60 s + los 720 s de tráfico normal), `ip_simuladas`.

### Prueba rápida en local (sin Kubernetes)

Redis y PostgreSQL en contenedores, un `java -jar taq.jar` por rol (`TAQ_ROLE`, `SERVER_PORT`, `TAQ_REDIS_URL`, `TAQ_DB_URL`, `TAQ_BLOQUEO_URL`…) y JMeter con la propiedades de arriba; `medir_recuperacion.py` y `verificar_exp3.py` aceptan `--deteccion/--respuesta/--bloqueo/--prom` para apuntar a los puertos locales. Así se hicieron las pruebas descritas abajo.

## Qué detecta el detector y por qué esos umbrales

Un ataque se define por el **comportamiento del actor**, no por el volumen total (la plataforma no sabe si está en un pico). Un comprador legítimo del generador hace 1 reserva (+1 confirmación) en total; un bot hace ~10 reservas por minuto y retiene lo que reserva.

| Parámetro | Valor | Justificación |
|---|---|---|
| `ventana_s` | 30 | Con 10 reservas/min un bot acumula 5 en la ventana; un comprador legítimo, 1–2. |
| `umbral_cuenta` | **3** reservas de una cuenta en la ventana | Un legítimo no llega (1 reserva; 2 con un reintento). Un bot llega en su 3.ª solicitud, unos 12 s después de empezar (tiempo de la marca, no de la detección: S-1 mide desde que el evento entra al detector). 2 sería demasiado cercano a un reintento humano; 4 retrasaría la marca 6 s y dejaría pasar más solicitudes fraudulentas. |
| `umbral_asientos` | 9 asientos pedidos por cuenta en la ventana | Un legítimo pide hasta 4 por solicitud; más de 9 en 30 s es acaparar. Regla de respaldo para quien pida grupos grandes. |
| `umbral_ip` | 20 solicitudes de una misma IP en la ventana | Solo se aplica a IP de cliente (`X-Forwarded-For`); detrás de un balanceador la IP remota es la del balanceador y no identifica a nadie. Cada bot usa su IP (≈5 solicitudes en la ventana), así que esta regla no dispara con el ataque del plan: cubre al atacante de una sola IP con muchas cuentas. 0 la desactiva. |

Se pueden cambiar sin reiniciar: `curl -X PUT -H 'Content-Type: application/json' -d '{"umbral_cuenta":4}' http://localhost:30091/parametros` (cada réplica del detector los relee de Redis en ≤ 5 s). **La tasa de falsos positivos solo está validada contra el tráfico legítimo del generador**, no contra compradores reales; el ASR S-1 declara que no la valida.

## Decisiones y desviaciones del plan (revisar)

1. **Cancelación de órdenes.** `reserva_log` es un registro de solo anexar, sin unicidad ni índice por comprador, y se llena de forma asíncrona. En vez de actualizarla (escaneo completo y condiciones de carrera con la persistencia), la cancelación se anota en la tabla nueva `orden_cancelada` (una fila por solicitud retenida que se liberó, con sus asientos). El conjunto de órdenes sale de la propia respuesta de `bd_bloqueo` (la fuente de verdad de lo que estaba retenido). Si se prefiere marcarlo en `reserva_log`, hay que agregarle un índice por comprador.
2. **Qué cuenta dentro de los 300 ms de S-2.** Alerta → revocación en Redis → liberación en `bd_bloqueo` (por su hilo único) → transacción en Postgres con `cuenta_revocada` y `orden_cancelada`. Queda **fuera** del tiempo, y se escribe después, la evidencia de recuperación en `bd_auditoria` (4 filas por cuenta), como "limpieza definitiva asíncrona" del ASR. El gateway tarda hasta ~1 s en dejar de aceptar la cuenta (copia local), pero `bd_bloqueo` rechaza desde el instante de la liberación las reservas de esa cuenta que ya iban en la cola (`CUENTA_REVOCADA`), así que no se retienen asientos nuevos.
3. **Revocar en bd_bloqueo.** `POST /bloqueo/liberar-comprador` con `revocar:true` añade al comprador a un conjunto en memoria del hilo único; es un añadido al diseño del plan, necesario para que una solicitud en vuelo no vuelva a bloquear asientos justo después de liberarlos.
4. **Reloj de S-2.** Se mide con el reloj de los pods (alerta en el detector, fin en el pod de respuesta); depende de que los nodos estén sincronizados por NTP (en EKS, Amazon Time Sync). `medir_recuperacion.py` usa también solo relojes de pods (no el de la máquina del usuario).
5. **Eventos del gateway.** Se publican tanto `reservar` como `confirmar`. La regla por cuenta cuenta solo `reservar`. Un 403 `CUENTA_REVOCADA` no se registra en `taq_reservar_seconds` (tiene su contador `taq_rechazos_cuenta_revocada_total`), así que no altera el histograma de EXP-1/2. Las reservas de los bots **sí** están en `taq_reservar_seconds` (son tráfico real al gateway): el p95 de Grafana mezcla ~12 % de bots; el p95 exacto del tráfico legítimo sale de la bitácora (`verificar_exp3.py`).
6. **IP simulada del tráfico legítimo.** Con ataques activos, el generador envía también `X-Forwarded-For` en el tráfico legítimo (una IP `10.x.y.z` por comprador, derivada de `c<n>`); si no, todo el tráfico legítimo llegaría con la IP del pod JMeter. Solo ocurre si `ataques_*` > 0 o `ip_simuladas=true`.
7. **Asientos de los bots.** Salen de los asientos que el tráfico normal y los conflictos no usan (los "frescos" sobrantes más los que están por encima del último bloque de conflictos), sin repetir ninguno (repetirlos haría creer al verificador D-3 que hay doble reserva). Con 40 ataques × 100 bots, el tope por bot (`duracion_max_ataque_s` × tasa) se reduce si no hay asientos suficientes; el valor efectivo queda en `ejecucion.json → exp3.solicitudes_max_por_bot`.
8. **Bitácora.** Con ataques se agrega al **final** la columna `ip`. Los bots se registran con `tipo=ATAQUE_BOT`, `grupo=<id del ataque>` (`A1`, `A2`…), `comprador=bot-A<n>-<i>`. Los lectores existentes (`Verificador`, `recolectar*.py`) leen por posición o por nombre de columna y se probaron con ese archivo.
9. **Estado de las marcas.** El detector es en memoria: si se reinicia, olvida ventanas y marcas locales (el conjunto Redis `cuentas_marcadas` evita doble marca entre réplicas, y `reiniciar-estado-exp3.sh` lo borra entre corridas). Con varias réplicas del detector cada una vería solo parte de las solicitudes de una cuenta; el experimento usa una réplica (los eventos de una cuenta no se reparten por clave).
10. **Marca masiva por IP.** Si una IP supera el umbral, se marcan en secuencia todas las cuentas vistas en su ventana desde un mismo hilo; con cientos de cuentas por IP los últimos tardarían más de 100 ms. No ocurre con el ataque del plan (una cuenta por IP).
11. **Medición independiente.** Consulta HTTP al estado real (hilo único de `bd_bloqueo` + Redis + Postgres vía el pod `respuesta`), por lo que añade una pequeña carga de lectura durante la recuperación y sus consultas a `bd_bloqueo` esperan en la misma cola. La cota es superior (la consulta llega unos ms después del cambio de estado).

## Verificación

`verificar_exp3.py <carpeta>` escribe `verificacion.md/json`. Criterios: todos los ataques y todos los bots marcados; 0 compradores legítimos marcados o revocados; 0 asientos de bots bloqueados al final; asientos liberados = asientos obtenidos por los bots (bitácora); órdenes canceladas = lo mismo; cuentas revocadas = bots; p95 de detección ≤ 100 ms y p95 de recuperación ≤ 300 ms por fase (normal y pico; Prometheus + auditoría + medida independiente). También informa: solicitudes fraudulentas que pasaron antes de la marca, p95 del tráfico legítimo dentro y fuera de las ventanas de recuperación (bitácora), y profundidad máxima de `cola_evento_trafico`, `cola_operacion` y `cola_alerta` por fase. Sale con código 0 solo si todo cumple. El D-3 de EXP-1 se corre sobre la misma bitácora (los bots no deben producir dobles reservas).

## Tablero

`aws/dashboards/gen-dashboard-exp3.py` → `exp3-dashboard.yaml` (ConfigMap, `monitoring`, etiqueta `grafana_dashboard: "1"`, uid `exp3asr`) y `exp3-dashboard-local.yaml` (mismo contenido; no usa métricas de Kubernetes). Solo S-1 y S-2: p95 de detección vs 100 ms, p95 de recuperación vs 300 ms (verde/rojo), % dentro del límite, cuentas marcadas vs bots inyectados (`BOTS_ESPERADOS`), cola de eventos y descartes, etapas de la recuperación, cola de operaciones durante la liberación masiva, p95 de reservar vs 250 ms y compradores legítimos marcados. Sin paneles de CPU ni memoria. No se ha cargado en ningún Grafana.

## Qué falta

- Construir y publicar la imagen `1.1`, aplicar los manifiestos y correr `run-exp3.sh` en EKS (humo primero, luego 2 corridas con semillas distintas).
- Validar a escala: la detección y la recuperación en el pico de 8.000/min, con la cola real de `bd_bloqueo`; el rendimiento del detector (4 hilos, un INSERT por marca) con 100 marcas casi simultáneas; la ocupación del nodo `sistema`.
- Comprobar el PodMonitor con los dos pods nuevos y las consultas del tablero contra el Prometheus real (las consultas de `verificar_exp3.py` se probaron contra un Prometheus local, el tablero no).
- Confirmar con medidas reales que `EXP-1/EXP-2` no cambian con la imagen 1.1 y `TAQ_DETECCION=off` (solo se comprobó que el comportamiento funcional, las métricas expuestas y la bitácora son los mismos).
