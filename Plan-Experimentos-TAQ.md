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

- **L-1:** con 400 solicitudes de reserva por minuto y una réplica, el p95 de reservar un asiento es ≤ 150 ms.
- **D-3:** aun cuando se inyectan al azar solicitudes simultáneas sobre un mismo asiento, o sobre grupos de asientos que se cruzan, solo una solicitud obtiene cada asiento. Las demás se rechazan sin dejar bloqueado ninguno de sus asientos, y no queda ningún asiento con más de una reserva.

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

- **E-1:** si cada tipo de pod escala solo, con un máximo de 8 réplicas, entonces con 8.000 solicitudes de reserva por minuto sostenidas 15 min el sistema se estabiliza con 8 réplicas o menos por pod y el p95 de reservar es < 250 ms. El hilo único de `bd_bloqueo` atiende esa carga sin ser el cuello de botella.
- **D-3:** aun en el pico, con varias réplicas compitiendo por el mismo `bd_bloqueo` y conflictos inyectados al azar, no queda ningún asiento con más de una reserva ni ningún bloqueo parcial.

### 2. Tácticas a probar

- **E-1:** Escalado horizontal (automático), Encolar solicitudes, Acotar el tamaño de colas e Introducir concurrencia.
- **D-3:** Transacciones.

### 3. Cómo se comprobará

**Qué se va a hacer.** Se ejecuta una sola corrida continua de unos 18 min que parte del tráfico normal, sube en rampa al pico y lo sostiene 15 min. La historia es la misma de EXP-1: llegadas aleatorias, compradores que confirman o abandonan y conflictos sobre los mismos asientos. Los pods no se escalan a mano: se programa el autoescalado y se observa en qué punto se equilibra el sistema. Grafana muestra la corrida en vivo.

**Cómo se va a hacer.** La corrida arranca con 1 min de calentamiento a 400 por minuto, con una réplica por pod. Luego la tasa sube a 8.000 por minuto en una rampa de unos 2 min y se sostiene 15 min. Cada tipo de pod que escala (`nodo_entrada` y `nodo_reserva`, y `nodo_pasarela` si la carga de pagos lo pide) lleva un autoescalador con mínimo de 1 réplica y máximo de 8, con un objetivo de uso de CPU de 60%. `bd_bloqueo` no escala, porque es un único hilo. Los conflictos se inyectan con la misma frecuencia y los mismos tipos que en EXP-1. El evento de prueba lleva unos 130.000 asientos, para que no falten en el pico. Como la cola de entrada está acotada, las solicitudes que no caben se rechazan rápido, y esos rechazos se cuentan aparte.

**Cómo se va a ejecutar.** Son 2 ejecuciones completas de la misma historia, con semillas distintas, con el autoescalado programado en todos los pods. No se fija de antemano a cuántas réplicas se equilibra cada pod. Se observa en cuántas se estabiliza el número de réplicas, y si coincide entre las dos ejecuciones. Al terminar, el mismo verificador de EXP-1 cruza la bitácora con `esquema_reserva` y con el estado de `bd_bloqueo`.

**Qué se va a probar.** Que el sistema, al escalar solo hasta 8 réplicas por pod, se equilibra y sostiene el pico con la latencia del ASR. Que el hilo único no limita ese pico. Que la exclusión y el todo o nada del bloqueo se mantienen mientras las réplicas aparecen y compiten por el mismo `bd_bloqueo`. Y que los bloqueos abandonados vencen también bajo carga.

**Componentes que se ejecutan.** Los mismos de EXP-1, con las réplicas que el autoescalado vaya creando.

**Métricas que se miden**

- **E-1:** el p95 de reservar, calculado en Prometheus desde que la solicitud entra al gateway hasta la respuesta. El p95 principal cubre los 15 min completos, incluido el arranque de las réplicas; además se reporta el p95 solo después de que el sistema se equilibra. Se documentan el p95 que ve el generador de carga, los errores y los rechazos por cola llena.
- **Equilibrio:** réplicas de cada pod a lo largo del tiempo, momento en que se estabilizan, tiempo que tardan en arrancar y nodos que EKS tuvo que agregar. CPU y memoria por réplica.
- **Hilo único:** operaciones por segundo que atiende, profundidad de `cola_operacion` y porcentaje de tiempo ocupado. Como dato adicional, su techo de operaciones por segundo contra las unas 133 por segundo del pico.
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

- **S-1:** si `componente_api_gateway` publica cada solicitud como evento en `cola_evento_trafico` y `componente_deteccion_ataque` las evalúa de forma asíncrona, entonces un ataque de reventa se detecta en ≤ 100 ms desde que el evento llega al detector, tanto en operación normal como en el pico.
- **S-2:** si `componente_respuesta_ataque` revoca el acceso y restaura el estado apoyándose en un índice en memoria, entonces tras la alerta del detector quedan liberados los asientos retenidos, canceladas las órdenes y revocadas las cuentas en ≤ 300 ms, sin afectar a los demás compradores.

### 2. Tácticas a probar

- **S-1:** Detectar intrusión, Detectar denegación de servicio y Mantener un registro de auditoría.
- **S-2:** Revocar el acceso y Restaurar el estado.

### 3. Cómo se comprobará

**Qué se va a hacer.** Se ejecuta una corrida continua con el tráfico legítimo de fondo de los experimentos anteriores. En instantes aleatorios se inyecta un ataque de reventa: bots desde muchas IP y cuentas que reservan asientos para retenerlos. Se mide cuánto tarda la detección y cuánto tarda la recuperación, primero con tráfico normal y después en el pico. Grafana permite seguir la corrida en vivo.

**Cómo se va a hacer.** El ataque se define por el comportamiento de cada actor, no por el volumen total, porque la plataforma no sabe si está en un pico. Cada ataque son 100 IP simuladas, con una cabecera distinta por hilo del generador, y una cuenta por bot. Cada bot manda unas 10 solicitudes por minuto, 1.000 por minuto en total. Los bots reservan asientos para retenerlos, de modo que al momento de la recuperación hay unos 100 asientos retenidos. Un comprador legítimo envía muchas menos solicitudes por minuto, y eso es lo que distingue a uno de otro en normal y en pico.

La corrida tiene 1 min de calentamiento y 12 min de tráfico normal, con 30 ataques en instantes aleatorios. Después una rampa de 2 min al pico de 8.000 por minuto y 10 min de pico con 10 ataques más, también en instantes aleatorios. En el pico rige el mismo autoescalado de EXP-2.

**Cómo se va a ejecutar.** Es una sola secuencia automatizada, con las pasarelas simuladas. Se ejecuta 2 veces con semillas distintas, 80 ataques en total. Al terminar cada ejecución, un script cruza la bitácora de lo que envió el generador con los registros de `bd_auditoria` y con el estado final de asientos, órdenes y cuentas.

**Qué se va a probar.** Que el detector marca el ataque a tiempo sin frenar la solicitud del comprador, porque el gateway publica y sigue. Que la recuperación libera asientos, cancela órdenes y revoca cuentas sin afectar a los demás compradores. Y que la liberación masiva en el pico, que entra por la cola del único hilo de `bd_bloqueo`, no frena a las reservas legítimas.

**Componentes que se ejecutan.** `componente_api_gateway`, `cola_evento_trafico`, `componente_deteccion_ataque`, `bd_auditoria`, `componente_respuesta_ataque` (con `componente_revocacion_acceso` y `componente_restauracion_estado`), `bd_bloqueo`, `bd_reserva`, `componente_parametrizacion` (reglas antifraude) y el flujo de reservar como tráfico de fondo.

**Métricas que se miden**

- **S-1:** el tiempo entre que el evento entra al detector y que queda registrada la evidencia en `bd_auditoria`, como histograma en Prometheus, con p95 por ventana (normal y pico). Dato adicional: cuántas solicitudes fraudulentas pasaron antes de la marca, porque la detección es asíncrona.
- **S-2:** el tiempo desde la alerta del detector hasta que los asientos están liberados, las órdenes canceladas y las cuentas revocadas, medido con un script que consulta el estado cada pocos milisegundos. Dato adicional: el p95 del tráfico legítimo durante la recuperación.
- **En el pico:** la profundidad máxima de `cola_evento_trafico`, la profundidad de `cola_operacion` durante la liberación masiva y cuántos compradores legítimos fueron marcados como sospechosos (se espera 0).
- **Monitoreo:** Grafana muestra en tableros las latencias de detección y de recuperación, las colas y el tráfico legítimo, en vivo y al terminar, y los tableros se guardan como evidencia.

### 4. Recursos requeridos

- **Lenguaje:** Java 17 (Spring Boot) para el detector y la respuesta. JMeter con scripts en Groovy para el tráfico de fondo y los ataques.
- **Local:** minikube y Docker, con Prometheus, Grafana, PostgreSQL 16, JMeter y un broker ligero para las colas. Hardware: la máquina del equipo.
- **Nube:** AWS EKS con los mismos manifiestos y Prometheus y Grafana en el clúster. La ejecución en la nube está sujeta a los tiempos de experimentación que tenemos.

### 5. Elementos de arquitectura involucrados

`componente_borde` (gateway, `cola_evento_trafico` y detección), `componente_respuesta_ataque`, `bd_auditoria`, `componente_servicio_reserva` (el flujo de reservar y `bd_bloqueo`), `bd_reserva` y `componente_parametrizacion`. Páginas 1, 4 y 7 de los diagramas.

### 6. Esfuerzo estimado

25 horas-persona.
