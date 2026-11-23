# Plan de experimentación — Plataforma TAQ (ARTI4109, Grupo 2)

Documento de trabajo. Cada experimento se agrega solo después de que el equipo lo aprueba.
ASRs: ver `ASRs-TAQ.md`. Tácticas: ver `Tacticas-TAQ.md`. Arquitectura: `Arquitectura-TAQ.drawio`.

## Decisiones generales

- **Herramientas:** JMeter genera la carga, Prometheus mide la métrica real de cada ASR dentro de la plataforma y Grafana muestra los tableros para monitorear cada corrida en vivo.
- **Entorno:** Kubernetes local con minikube, con posibilidad de pasar a AWS EKS. Son los mismos manifiestos. La ejecución en la nube está sujeta a los tiempos de experimentación que tenemos.
- **Pasarelas de pago:** simuladas, con latencia fija y fallas inyectables.
- **Frontera de medición:** JMeter mide desde el cliente (incluye red local y kube-proxy). El ASR se mide desde que la solicitud entra al `componente_api_gateway`, con Prometheus. Siempre se documenta la diferencia entre las dos cifras.

## Experimentos

| Experimento | ASRs | Tipo | Qué se prueba | Estado | Prioridad |
|---|---|---|---|---|---|
| EXP-1 | L-1, D-3 | Código | Corrida en operación normal con conflictos inyectados al azar | aprobado | priorizado |
| EXP-2 | E-1, D-3 | Código | Corrida con rampa al pico, autoescalado y conflictos inyectados al azar | aprobado | priorizado |
| EXP-3 | S-1, S-2 | Código | Ataques inyectados al azar en la corrida normal y en el pico; mide detección y recuperación | aprobado | S-1 priorizado; S-2 subpriorizado |

**Prioridad:** ver `ASRs-TAQ.md`. Los 4 ASRs priorizados son D-3, L-1, E-1 y S-1. S-2 (subpriorizado) se prueba dentro de EXP-3. Los demás ASRs subpriorizados y sin priorizar no tienen experimento por ahora.

---

## EXP-1 — Reserva de asientos en operación normal (L-1 y D-3)  ✅ aprobado

### 1. Hipótesis

Con la carga normal de reservas y una sola réplica, reservar un asiento cumple el tiempo de respuesta definido. Aun cuando se inyectan al azar solicitudes simultáneas sobre un mismo asiento, o sobre grupos de asientos que se cruzan, solo una solicitud obtiene cada asiento. Las demás se rechazan sin dejar bloqueado ninguno de los suyos, y ningún asiento queda con más de una reserva.

### 2. Tácticas a probar

- **L-1:** Introducir concurrencia, Caché hit / caché miss, Acotar el tamaño de colas y Reducir la sobrecarga.
- **D-3:** Transacciones.

### 3. Cómo se comprobará

**Qué se va a hacer.** Se ejecuta una sola corrida continua de unos 13 min que simula una preventa en operación normal: compradores que llegan de forma aleatoria a 400 por minuto. Durante toda la corrida se inyectan al azar conflictos sobre los mismos asientos. Se mide la latencia de reservar y se comprueba que no hay doble reserva. Grafana permite seguir la corrida en vivo.

**Cómo se va a hacer.** El generador de carga crea compradores virtuales con llegadas aleatorias y una tasa media de 400 por minuto. Cada uno pide un asiento. Una parte lo confirma con el pago y otra lo abandona (70% confirma y 30% abandona). Los abandonados dejan el bloqueo a los 8 min, y como la corrida dura más que eso, el vencimiento se comprueba sin acortarlo. Para verlo, el guion vuelve a pedir esos asientos a los 4 min, donde se espera rechazo, y después de los 8 min, donde se espera éxito.

Con cierta probabilidad (una de cada 20 llegadas), la llegada dispara un conflicto de entre 5 y 10 solicitudes. Puede ser de tres tipos: varias solicitudes a la vez por el mismo asiento, grupos de 2 a 4 asientos que se cruzan (el 12-13 contra el 13-14), o una nueva solicitud sobre un asiento ya vendido. Cada corrida guarda su semilla aleatoria para poder repetirse.

**Cómo se va a ejecutar.** Es una sola secuencia automatizada en minikube, con las pasarelas simuladas. La corrida tiene 1 min de calentamiento y 12 min de tráfico normal con una sola réplica de reserva. Se repite 3 veces, cada vez con una semilla distinta. Al terminar cada corrida, un script cruza la bitácora de cada solicitud (asiento, comprador, resultado y hora) con el estado final de `esquema_reserva` y con una consulta de estado que se hace pasar por la cola de `bd_bloqueo`, para no saltarse a su hilo único.

**Qué se va a probar.** Que reservar es rápido en operación normal. Que el bloqueo excluye y es de todo o nada bajo conflictos aleatorios. Que un asiento vendido se rechaza y que un bloqueo abandonado vence a los 8 min. Con una sola réplica no se prueba la competencia entre réplicas; eso lo cubre EXP-2 con 2, 4 y 8.

**Componentes que se ejecutan.** El flujo de reservar completo: gateway, `cola_solicitud`, receptor, gestor, `bd_bloqueo`, consultor con `cache_asiento` (y `bd_reserva` si hay miss) y `cola_respuesta`. También el flujo de confirmar compra: confirmador y pasarela simulada.

**Métricas que se miden**

- **L-1:** el p95 del tiempo desde que la solicitud entra al gateway hasta que sale la respuesta, medido en Prometheus sobre los 12 min de tráfico normal. El p95 que ve el generador de carga se documenta aparte, con la diferencia.
- **D-3:** asientos con más de una reserva (se espera 0), bloqueos parciales (se espera 0), conflictos con exactamente un ganador, asientos vendidos rechazados y bloqueos abandonados liberados. Como dato adicional, el tiempo real entre el bloqueo y la liberación.
- **Monitoreo:** Grafana muestra en tableros el p95, la CPU y la memoria, la profundidad de las colas y la ocupación del hilo único, en vivo y al terminar la corrida. Los tableros se guardan como evidencia.

### 4. Recursos requeridos

- **Lenguaje:** Java 17 para los componentes (Spring Boot) y para el verificador (JDBC). `bd_bloqueo` es un proceso con un ejecutor de un solo hilo sobre una cola. El generador de carga es JMeter (que corre en la JVM), con scripts en Groovy dentro de JMeter para las llegadas aleatorias a partir de una semilla y para inyectar los conflictos.
- **Local:** minikube, Docker, Prometheus con Grafana (tableros para monitorear la corrida en vivo), PostgreSQL 16, JMeter y un broker ligero para las colas (Redis o RabbitMQ, por confirmar). Librerías: Micrometer con el cliente de Prometheus en los componentes. Hardware: la máquina del equipo, registrando sus características para interpretar el resultado.
- **Nube:** AWS EKS con los mismos manifiestos, con Prometheus y Grafana en el clúster y PostgreSQL gestionado o en el clúster (por confirmar). La ejecución en la nube está sujeta a los tiempos de experimentación que tenemos.

### 5. Elementos de arquitectura involucrados

`componente_api_gateway`, `cola_solicitud`, `cola_respuesta`, `componente_receptor_solicitud`, `componente_gestor_bloqueo`, `proceso_bd_bloqueo` (con `cola_operacion`, `hilo_unico`, `estado_asiento` y `proceso_vencimiento`), `componente_consultor_asiento`, `cache_asiento`, `componente_confirmador_compra`, `bd_reserva` y la pasarela simulada. Páginas 1, 2, 3 y 7 de los diagramas.

### 6. Esfuerzo estimado

20 horas-persona.

---

## EXP-2 — Escalabilidad de reservas en el pico (E-1 y D-3)  ✅ aprobado

### 1. Hipótesis

Si cada tipo de pod escala solo, hasta un máximo de 8 réplicas, entonces con la carga del pico sostenida el sistema se estabiliza sin llegar a ese máximo y reservar cumple el tiempo de respuesta definido para el pico. El hilo único de `bd_bloqueo` atiende esa carga sin ser el cuello de botella. Además, aun con varias réplicas compitiendo por el mismo `bd_bloqueo` y con conflictos inyectados al azar, ningún asiento queda con más de una reserva ni con un bloqueo parcial. Como complemento exploratorio, tras el pico se sube la carga hasta 20.000 por minuto para observar cómo responde el autoescalado y dónde está el límite del sistema; esa fase no tiene umbral de ASR.

### 2. Tácticas a probar

- **E-1:** Escalado horizontal (automático), Encolar solicitudes, Acotar el tamaño de colas e Introducir concurrencia.
- **D-3:** Transacciones.

### 3. Cómo se comprobará

**Qué se va a hacer.** Se ejecuta una sola corrida continua de 10 min que parte del tráfico normal, sube rápido al pico de 8.000 por minuto, lo sostiene hasta el minuto 2 y después sigue subiendo hasta 20.000 por minuto, donde se mantiene hasta el final. La historia es la misma de EXP-1: llegadas aleatorias, compradores que confirman o abandonan y conflictos sobre los mismos asientos. Los pods no se escalan a mano: se programa el autoescalado y se observa en qué punto se equilibra el sistema. Grafana muestra la corrida en vivo.

**Cómo se va a hacer.** La corrida arranca a 400 por minuto con una réplica por pod. El perfil de carga, de 10 min en total, tiene cuatro tramos: del segundo 0 al 30 la tasa sube de 400 a 8.000 por minuto (el calentamiento es solo esa subida rápida); del segundo 30 al minuto 2 se sostiene en 8.000 por minuto; del minuto 2 al minuto 6 sube de forma lineal de 8.000 a 20.000 por minuto; y del minuto 6 al 10 se sostiene en 20.000 por minuto. Las llegadas siguen siendo aleatorias (Poisson) con tasa variable. Cada tipo de pod que escala (`nodo_entrada` y `nodo_reserva`, y `nodo_pasarela` si la carga de pagos lo pide) lleva un autoescalador con mínimo de 1 réplica y máximo de 8, con un objetivo de uso de CPU de 60%. `bd_bloqueo` no escala, porque es un único hilo. Los conflictos se inyectan con la misma frecuencia y los mismos tipos que en EXP-1 (1 de cada 20 llegadas), y sus solicitudes cuentan dentro de la tasa objetivo. El evento de prueba lleva 400.000 asientos en el catálogo, para que no falten en el perfil de 20.000 por minuto (unas 150.000 solicitudes en la corrida). Como la cola de entrada está acotada, las solicitudes que no caben se rechazan rápido, y esos rechazos se cuentan aparte.

**Cómo se va a ejecutar.** Es 1 ejecución completa (semilla 1), con el autoescalado programado en todos los pods. No se fija de antemano a cuántas réplicas se equilibra cada pod. Se observa cuántas réplicas tiene cada pod en cada tramo y si el número se estabiliza al sostener el pico de 8.000 por minuto y la meseta de 20.000. Al terminar, el mismo verificador de EXP-1 cruza la bitácora con `esquema_reserva` y con el estado de `bd_bloqueo`.

**Qué se va a probar.** Que el sistema, al escalar solo hasta 8 réplicas por pod, se equilibra y sostiene el pico con la latencia del ASR. Que el hilo único no limita ese pico. Que la exclusión y el todo o nada del bloqueo se mantienen mientras las réplicas aparecen y compiten por el mismo `bd_bloqueo`. Y que los bloqueos abandonados vencen también bajo carga.

**Componentes que se ejecutan.** Los mismos de EXP-1, con las réplicas que el autoescalado vaya creando.

**Métricas que se miden**

- **E-1:** el p95 de reservar, calculado en Prometheus desde que la solicitud entra al gateway hasta la respuesta, por tramo de la corrida. El veredicto de E-1 se toma sobre el tramo sostenido de 8.000 por minuto (segundo 30 al minuto 2, que incluye el arranque de las réplicas), con el umbral de p95 < 250 ms, sin errores y sin rechazos por cola llena. Este tramo dura 90 s y no los 15 min que pide el ASR; eso se reporta como limitación. Los tramos de subida a 20.000 y de meseta de 20.000 son exploratorios: se reporta su p95, las réplicas, los errores y los rechazos, y en qué punto el sistema se satura (p95 sobre 250 ms, rechazos por cola llena, hilo único ocupado o falta de nodos). También se documenta el p95 que ve el generador de carga.
- **Equilibrio:** réplicas de cada pod a lo largo del tiempo y por tramo, momento en que se estabilizan, tiempo que tardan en arrancar y nodos que EKS tuvo que agregar. CPU y memoria por réplica.
- **Hilo único:** operaciones por segundo que atiende, profundidad de `cola_operacion` y porcentaje de tiempo ocupado. Como dato adicional, su techo de operaciones por segundo contra las unas 133 por segundo del pico de 8.000 por minuto y las unas 333 por segundo de la meseta de 20.000.
- **D-3:** asientos con más de una reserva (se espera 0), bloqueos parciales (se espera 0), conflictos con exactamente un ganador, asientos vendidos rechazados y bloqueos abandonados liberados.
- **Monitoreo:** Grafana muestra en tableros el p95, las réplicas por pod, la CPU y la memoria, la profundidad de las colas y la ocupación del hilo único, en vivo y al terminar las ejecuciones. Los tableros se guardan como evidencia.

### 4. Recursos requeridos

- **Lenguaje:** Java 17 (Spring Boot) para los componentes y el verificador. JMeter (que corre en la JVM) con scripts en Groovy para la carga.
- **Local:** minikube y Docker, con Prometheus, Grafana, PostgreSQL 16, JMeter, un broker ligero para las colas (por confirmar) y el autoescalador de pods. Hardware: la máquina del equipo. Con 8 réplicas, las colas y los almacenes compiten por sus recursos en una sola máquina, y eso se anota para interpretar el resultado.
- **Nube:** AWS EKS con autoescalado de pods y de nodos y registro de imágenes. Prometheus y Grafana en el clúster, PostgreSQL (gestionado o en el clúster, por confirmar) y un broker ligero para las colas (por confirmar). JMeter en una instancia aparte, para que el generador de carga no sea el límite. Tipo y cantidad de nodos por definir. La ejecución en la nube está sujeta a los tiempos de experimentación que tenemos; si no alcanza, se ejecuta en local y se documentan las limitaciones.

### 5. Elementos de arquitectura involucrados

`eks_cluster`, `nodo_entrada` (×N), `nodo_reserva` (×N), `nodo_pasarela`, `nodo_memoria` (×1), `nodo_base_dato`, y los componentes de EXP-1: `componente_api_gateway`, `cola_solicitud`, `cola_respuesta`, `componente_receptor_solicitud`, `componente_gestor_bloqueo`, `proceso_bd_bloqueo`, `componente_consultor_asiento`, `cache_asiento`, `componente_confirmador_compra` y `bd_reserva`. Páginas 1, 2, 3, 4 y 7 de los diagramas.

### 6. Esfuerzo estimado

30 horas-persona.

---

## EXP-3 — Seguridad: detectar y recuperarse de un ataque (S-1 y S-2)  ✅ aprobado

### 1. Hipótesis

Si `componente_api_gateway` publica cada solicitud como evento en `cola_evento_trafico` y `componente_deteccion_ataque` las evalúa de forma asíncrona, entonces un ataque de reventa se detecta dentro del tiempo definido desde que el evento llega al detector, tanto con tráfico normal como en el pico. Si además `componente_respuesta_ataque` revoca el acceso y restaura el estado apoyándose en un índice en memoria, entonces tras la alerta quedan liberados los asientos retenidos, canceladas las órdenes y revocadas las cuentas dentro del tiempo definido, sin afectar a los demás compradores. Además, el tipo de atacante (bot individual, granja de cuentas o acaparador de asientos) viaja como una etiqueta en la solicitud, el detector la deja registrada junto a la evidencia, y ese registro es el reporte de seguridad que da pie a la recuperación.

### 2. Tácticas a probar

- **S-1:** Detectar intrusión, Detectar denegación de servicio y Mantener un registro de auditoría.
- **S-2:** Revocar el acceso y Restaurar el estado.

### 3. Cómo se comprobará

**Qué se va a hacer.** Se ejecuta una corrida continua con el tráfico legítimo de fondo de los experimentos anteriores. En instantes aleatorios se inyecta un ataque de reventa, de uno de tres tipos (bot individual, granja de cuentas o acaparador de asientos), con cuentas que reservan asientos para retenerlos. Se mide cuánto tarda la detección y cuánto tarda la recuperación, por tipo de ataque, primero con tráfico normal y después en el pico. Grafana permite seguir la corrida en vivo, con el ASR S-1 como protagonista del tablero.

**Cómo se va a hacer.** El ataque se define por el comportamiento de cada actor, no por el volumen total, porque la plataforma no sabe si está en un pico. Las IP son simuladas con una cabecera `X-Forwarded-For` que fija el generador. Un comprador legítimo envía muy pocas solicitudes por minuto (1 reserva, 2 con un reintento de los mismos asientos), y eso es lo que distingue a uno de otro en normal y en pico. Se inyectan **tres tipos de ataque**, y cada uno lo delata una señal distinta. **El tipo de atacante no lo deduce un algoritmo: lo declara el generador con una etiqueta `tipoAtacante` en el JSON de cada solicitud del ataque** (`bot_individual`, `granja_cuentas` o `acaparador`). El gateway la copia al evento, el detector la copia al registro de `bd_auditoria`, a la alerta y a las métricas, y el tablero la muestra. La etiqueta es solo metadato para el reporte: el detector no la usa para decidir si hay ataque, y no se construye ningún clasificador, porque no es el fin del experimento. La detección sigue siendo la de las reglas existentes, que son las de la tabla:

| Tipo de ataque | Cómo se comporta | Señal y regla que lo delata |
|---|---|---|
| **1. Bot individual** | 100 bots por ataque; cada bot tiene su propia IP y su propia cuenta y manda unas 10 reservas por minuto de asientos distintos (unas 1.000 por minuto en total) | Cuenta: `cuenta_frecuencia`, 3 o más reservas de una cuenta en la ventana de 30 s |
| **2. Granja de cuentas** | 100 cuentas por ataque detrás de una sola IP; cada cuenta manda unas 3 reservas por minuto, de modo que ninguna alcanza sola el umbral por cuenta, pero la IP junta unas 300 por minuto | IP: `ip_frecuencia` e `ip_marcada`, 20 o más solicitudes de una misma IP en la ventana; al marcarla se marcan todas las cuentas vistas desde esa IP |
| **3. Acaparador de asientos** | 20 cuentas por ataque, cada una con su IP, que piden grupos de 4 asientos distintos (el máximo por solicitud), unas 5 solicitudes por minuto | Asientos: `cuenta_asientos`, más de 7 asientos pedidos por una cuenta en la ventana (parámetro `umbral_asientos` = 7), antes de llegar al umbral de frecuencia |

**Dos versiones del algoritmo de marca y recuperación en bloque.** Un ensayo previo mostró que la marca en bloque de una granja (todas las cuentas de una IP) escribía la evidencia cuenta por cuenta, en un solo hilo, y que cada cuenta pagaba el trabajo de las anteriores: con 30 cuentas el p95 de detección fue de 182 ms (límite de 100 ms) y el de recuperación de 234 ms (límite de 300 ms). Esa versión (v1) se conserva como línea base. La versión que se usa en las ejecuciones oficiales (v2) escribe la evidencia de todas las cuentas en una sola operación y la recuperación se procesa en lote; no cambia las reglas, los umbrales ni la etiqueta. El reporte compara ambas versiones. Los umbrales son parámetros del componente de parametrización y se pueden cambiar sin reiniciar. Los bots reservan asientos para retenerlos, de modo que al momento de la recuperación hay asientos retenidos por cada cuenta atacante. **Quedan fuera de alcance**: el ataque que rota de dispositivo (el detector no cuenta por dispositivo), la inundación por denegación de servicio y los ataques de bajo volumen que se quedan bajo el umbral; el ASR S-1 no valida estos últimos. Limitación conocida: con `umbral_asientos` = 7 un comprador legítimo que reintentara con los mismos 4 asientos sumaría 8 y se marcaría; el generador de los compradores legítimos no hace reintentos. La respuesta de S-1 "alertar al equipo de operaciones" se cubre con la alerta interna que consume `componente_respuesta_ataque` y con el reporte de seguridad visible en Grafana; no se envía una notificación externa a una persona. La tasa de falsos positivos no la valida el ASR, pero se mide como dato adicional (se espera 0 compradores legítimos marcados) y se reporta en la verificación, no en el tablero.

La corrida tiene 1 min de calentamiento y 12 min de tráfico normal, con 30 ataques en instantes aleatorios. Después una rampa de 2 min al pico de 8.000 por minuto y 10 min de pico con 10 ataques más, también en instantes aleatorios. Los ataques se reparten por turnos, en partes casi iguales y de forma determinista con la semilla, entre los tres tipos (en la fase normal 10 de cada tipo; en el pico 3, 3 y 4). En el pico rige el mismo autoescalado de EXP-2.

**Cómo se va a ejecutar.** Es una sola secuencia automatizada, con las pasarelas simuladas. Se ejecuta 2 veces con semillas distintas, 80 ataques en total. Al terminar cada ejecución, un script cruza la bitácora de lo que envió el generador (que registra el tipo de ataque inyectado) con los registros de `bd_auditoria` y con el estado final de asientos, órdenes y cuentas. La medida independiente de la recuperación corre dentro del clúster, en la misma red que el sistema, para no medir la latencia de la conexión del equipo desde el que se lanza la prueba.

**Qué se va a probar.** Que el detector marca el ataque a tiempo sin frenar la solicitud del comprador, porque el gateway publica y sigue. Que cada tipo de ataque (bot individual, granja de cuentas y acaparador) se detecta con las reglas existentes y queda registrado con su etiqueta en el reporte de seguridad. Que la recuperación libera asientos, cancela órdenes y revoca cuentas sin afectar a los demás compradores. Y que la liberación masiva en el pico, que entra por la cola del único hilo de `bd_bloqueo`, no frena a las reservas legítimas.

**Componentes que se ejecutan.** `componente_api_gateway`, `cola_evento_trafico`, `componente_deteccion_ataque`, `bd_auditoria`, `componente_respuesta_ataque` (con `componente_revocacion_acceso` y `componente_restauracion_estado`), `bd_bloqueo`, `bd_reserva`, `componente_parametrizacion` (reglas antifraude) y el flujo de reservar como tráfico de fondo.

**Métricas que se miden**

- **S-1:** el tiempo entre que el evento entra al detector (se toma de la cola de tráfico) y que queda registrada la evidencia en `bd_auditoria`, como histograma en Prometheus, con p50, p95 y p99 por ventana (normal y pico). La espera del evento en la cola se mide aparte, y se reporta junto con la profundidad de la cola. **Por tipo de ataque (etiqueta):** ataques inyectados y cuentas marcadas, qué regla disparó cada marca, el p95 de detección y las solicitudes que pasaron antes de la marca, y que todos los ataques de cada tipo se detectaron. Dato adicional: cuántas solicitudes fraudulentas pasaron antes de la marca, porque la detección es asíncrona.
- **S-2:** el tiempo desde la alerta del detector hasta que los asientos están liberados, las órdenes canceladas y las cuentas revocadas, medido con un script que consulta el estado cada pocos milisegundos. Dato adicional: el p95 del tráfico legítimo durante la recuperación. Los 300 ms miden que la revocación quedó registrada; el gateway puede tardar hasta 1 s en empezar a rechazar a la cuenta (refresca su lista cada segundo), y las solicitudes de atacantes que pasan en esa ventana se cuentan aparte.
- **En el pico:** la profundidad máxima de `cola_evento_trafico`, la profundidad de `cola_operacion` durante la liberación masiva y cuántos compradores legítimos fueron marcados como sospechosos (se espera 0).
- **Monitoreo:** Grafana muestra un tablero compacto con el ASR S-1 como protagonista (p50, p95 y p99 de detección contra 100 ms, % dentro del límite, cuentas marcadas), el tipo de atacante según su etiqueta (cuentas marcadas por minuto y por tipo), el reporte de seguridad leído de `bd_auditoria` (resumen por tipo y últimas marcas, con cuenta, IP y hora) y, al final, el ASR S-2 (p95 de recuperación contra 300 ms, asientos liberados, órdenes canceladas y cuentas revocadas). Un segundo tablero de detalle sirve para diagnosticar (etapas de la recuperación, colas y reglas). Se leen en vivo y al terminar, y los tableros se guardan como evidencia. La lectura de `bd_auditoria` usa el mismo Postgres que ya existe, como fuente de datos de Grafana, sin componentes nuevos.

### 4. Recursos requeridos

- **Lenguaje:** Java 17 (Spring Boot) para el detector y la respuesta. JMeter con scripts en Groovy para el tráfico de fondo y los ataques.
- **Local:** minikube y Docker, con Prometheus, Grafana, PostgreSQL 16, JMeter y un broker ligero para las colas. Hardware: la máquina del equipo.
- **Nube:** AWS EKS con los mismos manifiestos y Prometheus y Grafana en el clúster. La ejecución en la nube está sujeta a los tiempos de experimentación que tenemos.

### 5. Elementos de arquitectura involucrados

`componente_borde` (gateway, `cola_evento_trafico` y detección), `componente_respuesta_ataque`, `bd_auditoria`, `componente_servicio_reserva` (el flujo de reservar y `bd_bloqueo`), `bd_reserva` y `componente_parametrizacion`. Páginas 1, 4 y 7 de los diagramas.

### 6. Esfuerzo estimado

25 horas-persona.
