# ASRs — Plataforma TAQ (ARTI4109, Grupo 2)

Documento de trabajo. Cada ASR se agrega aquí solo después de que el equipo lo aprueba.
Contexto del enunciado: ver `MEMORIA-Contexto-Proyecto-TAQ.md`.

## Decisiones de alcance

- Atributos de calidad a verificar: **latencia, escalabilidad, seguridad, disponibilidad, modificabilidad e interoperabilidad**.
- **Latencia:** umbral de **150 ms en p95** (más estricto que el 1 s del enunciado; decisión del equipo). La latencia se mide solo en régimen normal; el pico de carga se evalúa en escalabilidad.
- **Seguridad:** solo ASRs de detectar y recuperarse de ataques. Resistir ataques (bots, límite de 4 boletas por persona, boletas falsificadas) no es un ASR; se maneja de forma implícita en el diseño de la arquitectura.
- **Disponibilidad:** se entiende a nivel de software e incluye (a) que el valor del dato sea correcto (sin doble venta, precio único) y (b) detectar y recuperarse de fallas de software. No se trata de disponibilidad de hardware.
- **Disponibilidad (decisión final):** solo ASRs de detectar y recuperarse de la falla de un componente del pago (D-1, D-2). La doble venta de un asiento, el precio total único y la detección y recuperación de fallas de instancias se descartaron como ASRs; se manejan de forma implícita en el diseño de la arquitectura.
- **Modificabilidad:** el reemplazo de una pasarela en producción sin interrumpir ventas se descartó como ASR (implícito en el diseño). M-2 trata la modificación de la lógica de impuestos por país. La variación de impuestos por país es una extensión del equipo; el enunciado solo menciona precios con y sin impuestos y la apertura de 2 países más.
- Los ASRs marcados con ⚠️ usan cifras que el enunciado no da; son supuestos por confirmar.

## Lista de ASRs (13)

| Atributo | IDs | Estado |
|---|---|---|
| Latencia | L-1, L-2 | L-1 y L-2 aprobados |
| Escalabilidad | E-1, E-2 | E-1 y E-2 aprobados (la escalabilidad del control de acceso se descartó) |
| Seguridad | S-1 (detectar), S-2 (recuperarse) | S-1 y S-2 aprobados |
| Disponibilidad | D-1 (detectar falla en pagos), D-2 (recuperarse) | D-1 y D-2 aprobados |
| Modificabilidad | M-1, M-2, M-3 | M-1, M-2 y M-3 aprobados |
| Interoperabilidad | I-1, I-2 | I-1 y I-2 aprobados |

## ASRs priorizados para experimentar (9 de 13)

No se pueden atacar los 13 ASRs. El equipo priorizó estos 9, que son los que se llevan a experimentación:

| # | ID | ASR |
|---|---|---|
| 1 | L-1 | Latencia de confirmación de reserva |
| 3 | E-1 | Escalabilidad de reservas en preventa |
| 5 | S-1 | Detectar un ataque |
| 6 | S-2 | Recuperarse de un ataque |
| 7 | D-1 | Detectar la falla de un componente del pago |
| 8 | D-2 | Recuperarse de la falla de un componente del pago |
| 9 | M-1 | Incorporar una pasarela de pago nueva |
| 11 | M-3 | Cambiar reglas de forma gradual y reversible |
| 12 | I-1 | Interpretar los formatos de los promotores |

Sin priorizar (siguen aprobados y pueden retomarse): L-2 (latencia en puerta), E-2 (escalabilidad de pagos), M-2 (impuestos por país) e I-2 (lectores de distintos fabricantes). Con esta selección, el control de acceso en puerta queda sin ASR experimentado.

**L-2 es opcional, la última opción:** no está priorizado ni marcado en el Excel. Solo se implementa si sobra tiempo; comparte la plantilla de prueba de L-1.

El Excel `ASRs-TAQ.xlsx` marca los priorizados con la columna "Priorizado" y los subraya.

---

## L-1 — Latencia de confirmación de reserva  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Comprador desde la app web o móvil |
| **Estímulo** | Solicita reservar un asiento de un evento |
| **Patrón del estímulo** | Carga constante de 400 compras/min |
| **Artefacto** | Servicio de reservas e inventario de asientos |
| **Entorno** | Operación normal, sin picos ni fallas inyectadas |
| **Respuesta** | La plataforma confirma la reserva y bloquea el asiento para ese comprador durante 8 min |
| **Medida de respuesta** | p95 ≤ 150 ms |

**Hipótesis:** Si la reserva se resuelve con un bloqueo atómico en un almacén en memoria con expiración de 8 min, y la persistencia definitiva se hace de forma asíncrona mediante cola, entonces la latencia de confirmación será p95 ≤ 150 ms a 400 compras/min.

**No valida:** la latencia durante el pico de preventa (se mide en E-1), la latencia que percibe el comprador con su red, ni el comportamiento bajo fallas.

**Nota para E-1:** sostener 8.000 solicitudes/min durante 15 min sin perder solicitudes y medir la latencia del pico.

---

## L-2 — Latencia de validación de boleta en puerta  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Asistente que presenta su boleta en un lector de puerta, de cualquiera de los 3 fabricantes |
| **Estímulo** | Solicita ingresar al recinto con el código de su boleta |
| **Patrón del estímulo** | Carga constante de 300 validaciones/min |
| **Artefacto** | Servicio de validación de acceso |
| **Entorno** | Día del evento, operación normal, sin picos ni fallas inyectadas |
| **Respuesta** | El servicio verifica la autenticidad de la boleta, comprueba que no se haya usado, la marca como usada y responde si permite o niega el ingreso |
| **Medida de respuesta** | p95 ≤ 150 ms |

**Hipótesis:** Si el código de la boleta es verificable por firma y la marca de uso se hace con una operación atómica en un almacén en memoria, entonces la latencia de validación será p95 ≤ 150 ms a 300 validaciones/min.

**No valida:** el flujo máximo del estadio (ningún ASR lo evalúa), el tiempo del lector físico ni la red del recinto, ni el comportamiento bajo fallas.

---

## E-1 — Escalabilidad en preventa  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Compradores desde la app web o móvil |
| **Estímulo** | Solicitan reservar asientos de un evento de alta demanda al abrir la preventa |
| **Patrón del estímulo** | Aumento súbito de 400 a 8.000 solicitudes de reserva/min, sostenido durante 15 min |
| **Artefacto** | Servicio de reservas e inventario de asientos |
| **Entorno** | Alta demanda con 8.000 transacciones por minuto |
| **Respuesta** | La plataforma aumenta su capacidad, atiende todas las solicitudes y confirma las reservas |
| **Medida de respuesta** | p95 < 250 ms durante 15 min |

**Hipótesis:** Si los servicios de reserva son sin estado y escalan horizontalmente detrás de un balanceador, el bloqueo atómico en memoria se particiona por evento y la persistencia se hace de forma asíncrona mediante cola, entonces la plataforma sostendrá 8.000 transacciones/min durante 15 min con latencia p95 < 250 ms.

**No valida:** cargas por encima de 8.000/min, varios eventos de alta demanda al mismo tiempo, el comportamiento bajo fallas (D-3 a D-6) ni la latencia que percibe el comprador con su red.

---

## E-2 — Escalabilidad en pagos  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Compradores desde la app web o móvil |
| **Estímulo** | Confirman el pago de los asientos que reservaron |
| **Patrón del estímulo** | Aumento súbito de 400 a 8.000 pagos/min, sostenido durante 15 min |
| **Artefacto** | Orquestador de pagos |
| **Entorno** | Alta demanda con 8.000 transacciones por minuto |
| **Respuesta** | La plataforma aumenta su capacidad, procesa el pago a través de la pasarela y confirma la compra |
| **Medida de respuesta** | p95 < 250 ms durante 15 min |

**Hipótesis:** Si el orquestador de pagos es sin estado y escala horizontalmente, el envío a la pasarela es idempotente y con conexiones agrupadas, y el registro definitivo de la compra se hace de forma asíncrona mediante cola, entonces la plataforma sostendrá 8.000 pagos/min durante 15 min con latencia p95 < 250 ms.

**Frontera de medición:** se mide con una pasarela simulada de tiempo fijo; el tiempo de respuesta de la pasarela externa no cuenta.

**No valida:** el tiempo de respuesta de la pasarela externa, las fallas de pasarela (D-4, D-6) ni su reemplazo (M-2), ni cargas por encima de 8.000 pagos/min.

---

## S-1 — Detectar un ataque  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Organizaciones de reventa, con bots y cuentas fraudulentas |
| **Estímulo** | Lanzan un ataque coordinado de solicitudes automatizadas |
| **Patrón del estímulo** | Durante la operación normal y durante la hora pico de una preventa |
| **Artefacto** | Monitoreo de tráfico y motor antifraude |
| **Entorno** | Operación normal (400 transacciones/min) y alta demanda (8.000 transacciones/min) |
| **Respuesta** | Identifica el patrón de ataque, alerta al equipo de operaciones y registra la evidencia (IP, cuentas, horarios) |
| **Medida de respuesta** | Detección en ≤ 100 ms |

**Hipótesis:** Si el api_gateway publica cada solicitud como evento en una cola y el detector las evalúa de forma asíncrona contra contadores en memoria por IP, dispositivo y cuenta, y contra reglas de comportamiento, entonces el ataque se detectará en ≤ 100 ms desde que el evento llega al detector, sin retrasar la solicitud del comprador, tanto en operación normal como en hora pico.

**Interpretación de "detectar":** el detector marca como sospechosa una solicitud ≤ 100 ms después de recibir su evento de la cola de tráfico. El gateway no espera el resultado, así que las primeras solicitudes de un ataque pueden pasar antes de la marca; S-2 se encarga de recuperar. No es el reconocimiento del patrón agregado de un ataque, que suele tardar segundos.

**No valida:** el bloqueo del ataque ni la recuperación (S-2), los ataques de bajo volumen que no superen el umbral ni la tasa de falsos positivos.

---

## S-2 — Recuperarse de un ataque  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Motor antifraude, tras la alerta de S-1 |
| **Estímulo** | Un ataque ya detectado ha dejado asientos retenidos, órdenes y cuentas fraudulentas |
| **Patrón del estímulo** | Durante la operación normal y durante la hora pico de una preventa |
| **Artefacto** | Inventario de asientos, motor de reglas y gestión de cuentas |
| **Entorno** | Operación normal (400 transacciones/min) y alta demanda (8.000 transacciones/min) |
| **Respuesta** | Libera los asientos retenidos por los actores fraudulentos, cancela sus órdenes, bloquea sus cuentas y sigue atendiendo a los demás compradores |
| **Medida de respuesta** | Recuperación en ≤ 300 ms |

**Hipótesis:** Si cada reserva, orden y cuenta queda asociada a un identificador de actor en un índice en memoria, y la revocación en bloque de bloqueos y cuentas se aplica primero en memoria, con la limpieza definitiva de los registros hecha de forma asíncrona, entonces la plataforma se recuperará del ataque en ≤ 300 ms sin afectar las ventas de otros compradores.

**No valida:** la detección del ataque (S-1), la limpieza definitiva de los registros (ocurre después de los 300 ms), las boletas ya revendidas fuera de la plataforma ni los reembolsos de pagos ya cobrados.

---

## D-1 — Detectar la falla de un componente del pago  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Un componente del flujo de pago: la pasarela de pago u otro servicio que participa en el cobro |
| **Estímulo** | Deja de responder |
| **Patrón del estímulo** | Durante la operación normal |
| **Artefacto** | Orquestador de pagos y su monitoreo |
| **Entorno** | Operación normal (400 transacciones/min) |
| **Respuesta** | Detecta la falla, marca el componente como no disponible y registra y avisa del evento |
| **Medida de respuesta** | Detección en < 150 ms |

**Hipótesis:** Si cada llamada a la pasarela pasa por un disyuntor (circuit breaker) que aplica un límite de espera, y se verifica la salud de cada componente del pago de forma continua, entonces la caída de un componente se detectará en < 150 ms en operación normal.

**No valida:** la detección durante la hora pico, la conmutación a otra pasarela ni la recuperación, las fallas fuera del flujo de pago ni las fallas que no produzcan ninguna señal dentro de esos 150 ms.

---

## D-2 — Recuperarse de la falla de un componente del pago  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Orquestador de pagos, tras la detección de D-1 |
| **Estímulo** | Una pasarela de pago queda marcada como no disponible mientras un comprador está pagando |
| **Patrón del estímulo** | Durante la operación normal |
| **Artefacto** | Orquestador de pagos |
| **Entorno** | Operación normal (400 transacciones/min) |
| **Respuesta** | Redirige el pago a la otra pasarela, conserva el asiento reservado y reintenta el cobro sin duplicarlo |
| **Medida de respuesta** | Recuperación en ≤ 300 ms |

**Hipótesis:** Si el orquestador mantiene dos pasarelas activas detrás de una interfaz uniforme, cada pago lleva una clave de idempotencia y el bloqueo del asiento es independiente del cobro, entonces el pago se redirigirá a la otra pasarela en ≤ 300 ms desde que se marca la falla, sin perder el asiento ni duplicar el cobro.

**No valida:** la detección de la falla (D-1), el reemplazo planificado de una pasarela (M-2), la caída simultánea de las dos pasarelas ni el tiempo que tarda la segunda pasarela en procesar el pago.

---

## M-1 — Incorporar una pasarela de pago nueva  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Gerencia de TAQ |
| **Estímulo** | Solicita la incorporación de un nuevo motor de pago (una pasarela de pago nueva) |
| **Patrón del estímulo** | Cada vez que se abre operación en un país nuevo con su propia pasarela local (2 países más el próximo año) |
| **Artefacto** | Capa de integración de pagos y núcleo de venta |
| **Entorno** | Desarrollo de la plataforma |
| **Respuesta** | Se integra la pasarela nueva con toda su configuración, sin modificar los demás componentes ni otros servicios ya montados previamente |
| **Medida de respuesta** | ≤ 120 horas-hombre |

**Hipótesis:** Si cada pasarela de pago se integra detrás de una interfaz estable (puertos y adaptadores), y los adaptadores se registran por configuración, entonces incorporar un motor de pago nuevo requerirá ≤ 120 horas-hombre y ningún cambio en los demás componentes ni en los servicios ya montados.

**No valida:** el reemplazo de una pasarela en producción sin interrumpir ventas (M-2), la integración de promotores y de fabricantes de lectores, ni la contratación comercial y la homologación con la pasarela.

---

## M-2 — Modificar la lógica de impuestos de un país  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Gerencia de TAQ |
| **Estímulo** | Solicita modificar o agregar la forma de calcular los impuestos de un país |
| **Patrón del estímulo** | Cada vez que se abre operación en un país nuevo (2 más el próximo año) o cambia la normativa tributaria de un país |
| **Artefacto** | Componente de cálculo de impuestos |
| **Entorno** | Desarrollo de la plataforma |
| **Respuesta** | Se modifica o se agrega la lógica de impuestos de ese país sin modificar otros servicios ya montados previamente, ni las reglas de los otros países |
| **Medida de respuesta** | ≤ 40 horas-hombre |

**Hipótesis:** Si el cálculo de impuestos está aislado en un componente que tiene una regla independiente por país, cargada por configuración y versionada, entonces modificar o agregar la lógica de impuestos de un país requerirá ≤ 40 horas-hombre y ningún cambio en otros servicios ni en las reglas de otros países.

**No valida:** que las tarifas e impuestos aplicados sean legalmente correctos, la normalización de los precios que envían los promotores (I-1), el cambio de reglas de precios o antifraude (M-3) ni el reemplazo de una pasarela en producción.

---

## M-3 — Cambiar reglas de forma gradual y reversible  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Gerencia de TAQ |
| **Estímulo** | Solicita cambiar las reglas de detección de compradores automatizados o las reglas de precios |
| **Patrón del estímulo** | Casi cada semana |
| **Artefacto** | Motor de reglas |
| **Entorno** | Desarrollo de la plataforma para modificar las reglas, y producción con ventas en curso, en operación normal (400 transacciones/min), para aplicarlas y revertirlas |
| **Respuesta** | Se modifican las reglas, se aplican primero a una parte del tráfico y, si causan problemas, se revierten sin detener ninguna venta en curso |
| **Medida de respuesta** | Modificación de las reglas en ≤ 8 horas-hombre y reversión en ≤ 2 min |

**Hipótesis:** Si las reglas son datos versionados fuera del código, se despliegan de forma gradual por porcentaje de tráfico y la reversión vuelve a la versión anterior por configuración sin reiniciar servicios, entonces modificar las reglas requerirá ≤ 8 horas-hombre, el cambio se aplicará primero a una parte del tráfico y se podrá revertir en ≤ 2 min sin detener ventas en curso.

**Nota sobre el valor:** las 8 horas-hombre (un día de trabajo) se eligieron para que el ASR distinga una arquitectura con reglas como datos de una con reglas incrustadas en el código. Los 2 min vienen del enunciado.

**No valida:** que las reglas nuevas sean correctas o efectivas, el cambio de reglas durante la hora pico ni la detección y recuperación de ataques (S-1, S-2).

---

## I-1 — Interpretar los formatos de los promotores  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Promotor de eventos |
| **Estímulo** | Envía el mapa de localidades, los precios y las condiciones de un evento en el formato de su propio sistema, con precios que pueden incluir o no los impuestos |
| **Patrón del estímulo** | Cada vez que un promotor publica o actualiza un evento (unos 1.200 eventos al año, de más de 40 promotores) |
| **Artefacto** | Módulo de ingesta y normalización |
| **Entorno** | Operación normal |
| **Respuesta** | Convierte los registros válidos a un modelo común, identificando si el precio incluye impuestos, y aparta los registros inválidos con el motivo, para que no se publiquen |
| **Medida de respuesta** | 100% de los registros válidos interpretados correctamente y 100% de los registros inválidos apartados, sin pérdida de datos |

**Hipótesis:** Si el formato de cada promotor se traduce con un adaptador a un único modelo común que exige indicar si el precio incluye impuestos, y cada registro se valida antes de publicarse, con los inválidos guardados aparte y no descartados, entonces el 100% de los registros válidos se interpretará correctamente, el 100% de los inválidos se apartará y no se perderá ningún dato.

**Notas:** un registro que no indique si el precio incluye impuestos es inválido y se aparta. "Sin pérdida de datos" significa que los inválidos se guardan en una cuarentena, no se borran, para poder corregirlos y reenviarlos. Para medir el 100% se necesita un conjunto de registros de prueba con la respuesta correcta conocida, con válidos e inválidos de varios formatos.

**No valida:** la corrección de las tarifas de impuestos (M-2), la integración de pasarelas y lectores (I-2) ni la incorporación de promotores nuevos con formatos nunca vistos.

---

## I-2 — Interpretar las lecturas de los lectores de distintos fabricantes  ✅ aprobado

| Parte | Contenido |
|---|---|
| **Fuente del estímulo** | Lectores de códigos de 3 fabricantes diferentes, en la puerta del recinto |
| **Estímulo** | Envían la lectura de una boleta, cada uno en su propio protocolo y formato |
| **Patrón del estímulo** | Cada vez que un asistente presenta su boleta el día del evento |
| **Artefacto** | Capa de integración con lectores y servicio de validación de acceso |
| **Entorno** | Día del evento, operación normal (300 validaciones/min) |
| **Respuesta** | Traduce cada lectura a un mensaje común, valida la boleta y devuelve la respuesta en el formato que espera cada fabricante |
| **Medida de respuesta** | 100% de las lecturas válidas interpretadas correctamente y 100% de las lecturas inválidas rechazadas, sin pérdida de datos |

**Hipótesis:** Si cada fabricante de lectores se integra con un adaptador que traduce su protocolo a un único mensaje común de validación y devuelve la respuesta en su formato, y toda lectura queda registrada, entonces el 100% de las lecturas válidas se interpretará correctamente, el 100% de las inválidas se rechazará y no se perderá ninguna lectura.

**No valida:** la latencia de la validación (L-2), la incorporación de un fabricante nuevo ni las fallas del hardware de los lectores. La integración de pasarelas se cubre en M-1 y D-2.

---

## Estado final de la lista

Los 13 ASRs están aprobados. Siguiente etapa: definir la arquitectura y luego el diseño de los experimentos (código y encuesta a un arquitecto externo).
