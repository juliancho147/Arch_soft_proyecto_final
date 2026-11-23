# Resumen de las decisiones de arquitectura — TAQ

La solicitud del comprador entra por el api_gateway, se encola, se reserva el asiento y se cobra; en paralelo se vigila el tráfico. Aparte, los promotores alimentan el catálogo.

## 1. La solución en cinco bloques

| # | Bloque | Qué hace | ASRs |
|---|---|---|---|
| 1 | **Defensa contra ataques** | Vigila el tráfico en paralelo a la reserva y reacciona si hay un ataque. | S-1, S-2 |
| 2 | **Reserva de asientos** | Resuelve cada reserva en paralelo, con el asiento bloqueado y sin venderlo dos veces. | L-1, E-1 (y D-3) |
| 3 | **Pago con dos pasarelas** | Cobra por una pasarela y, si falla, por la otra, sin perder el asiento. | D-1, D-2, M-1 |
| 4 | **Ingesta de promotores** | Traduce el formato de cada promotor a un modelo común y aparta lo inválido. | I-1 |
| 5 | **Reglas y parámetros, fuera del código** | Las reglas antifraude, los precios y los parámetros de cada pasarela son datos versionados que se cambian sin tocar el núcleo. | M-1, M-3 |

### Cómo funciona cada bloque

1. **Defensa contra ataques.** El api_gateway publica un evento de tráfico en una cola y sigue con la reserva, sin esperar. El detector toma los eventos y los compara con patrones de bots y con la línea base del tráfico, usando contadores en memoria por IP, dispositivo y cuenta. Si el veredicto es sospechoso, registra la evidencia y alerta al componente de respuesta, que revoca el acceso del actor y restaura el inventario (libera los asientos retenidos y cancela las órdenes ilegítimas). Las primeras solicitudes de un ataque pueden pasar antes de la marca; para eso está la recuperación.
2. **Reserva de asientos.** Las solicitudes entran a una cola acotada y las réplicas de reserva las toman con pull, en paralelo. Una sola pieza, `componente_gestor_bloqueo`, bloquea el asiento durante 8 min con una operación atómica; otra consulta su estado en la caché y otra valida el bloqueo y guarda la reserva. La respuesta vuelve por otra cola, unida a su solicitud por un identificador de correlación. Si la carga sube, se agregan réplicas.
3. **Pago con dos pasarelas.** Un orquestador de pagos conoce solo una interfaz estable; detrás hay un adaptador por pasarela. Las dos pasarelas están activas y un verificador de salud las sondea. Si una falla, el orquestador reintenta por la otra con una clave de idempotencia, sin soltar el bloqueo del asiento. Una pasarela nueva es un adaptador nuevo, registrado por configuración.
4. **Ingesta de promotores.** Lo que envía el promotor se recibe sin interpretarlo y pasa por un bus. Un orquestador dirige cada registro: lo transforma con el adaptador de ese promotor, genera el modelo común (con la indicación de si el precio incluye impuestos) y publica en el catálogo. Los registros inválidos van a una cuarentena con su motivo, sin perderse.
5. **Reglas y parámetros.** Un componente de parametrización entrega las reglas antifraude al borde, los precios a las reservas y los parámetros de pasarela al orquestador de pagos. Un cambio de regla se aplica primero a un porcentaje del tráfico y se revierte volviendo a la versión anterior, sin reiniciar servicios ni detener ventas en curso.

## 2. Por qué esta forma responde a los requisitos

- **Detectar sin esperar:** el gateway publica un evento de tráfico y sigue, así la detección de bots no suma latencia a los compradores legítimos (S-1, L-1).
- **Cola acotada e instancias sin estado:** absorben el pico de la preventa y escalan agregando instancias (E-1).
- **Un solo componente ejecuta el bloqueo** con una operación atómica "bloquear si está libre": dos solicitudes simultáneas por el mismo asiento nunca lo obtienen las dos (D-3).
- **El asiento bloqueado es independiente del cobro:** una falla de pasarela no hace perder el asiento (D-2).
- **Un adaptador por pasarela y por promotor** deja el núcleo de venta intacto cuando llega uno nuevo (M-1, I-1).
- **Las reglas como datos** permiten cambiar, probar con parte del tráfico y revertir en minutos (M-3).

## 3. Decisiones clave

1. **La reserva se escribe directo y síncrono.** Se guarda en `bd_reserva` sin pasar por una cola de persistencia. Se decidió al revisar el diagrama de componentes.
2. **Lo asíncrono siempre pasa por una cola o bus.** Una flecha «async» solo existe con una cola o un bus en el camino. La respuesta de la reserva vuelve por `cola_respuesta` con un identificador de correlación. Leer de una cola es un «sync» pull.
3. **El bloqueo es atómico y expira solo.** Lo ejecuta un solo componente, `componente_gestor_bloqueo`, sobre `bd_bloqueo`, y vence a los 8 min. Es lo que garantiza que un asiento nunca se reserve dos veces (D-3, táctica Transacciones).
4. **Resistir ataques no es un ASR.** Bots, tope de 4 boletas y boletas falsas se resisten con decisiones implícitas del diseño. Los escenarios de seguridad miden detectar y recuperarse.
5. **Para la doble reserva solo hay prevención.** Se descartó el par de ASRs de detectar y recuperarse; quedó solo D-3.
6. **El bloqueo corre en un solo hilo dentro del almacén.** Un solo hilo en todo el servicio se descartó porque rompe E-1.
7. **Orquestación y no coreografía en la ingesta (I-1).** Con un coordinador central es más sencillo asegurar y comprobar que el 100 % de lo válido se interprete y el 100 % de lo inválido se aparte, sin pérdida de datos.
8. **Redundancia activa y no pasiva en el pago (D-2).** La conmutación de la redundancia pasiva pondría en riesgo los 300 ms.
9. **Latencia exigida de 150 ms (p95).** El enunciado pide menos de 1 s; es una exigencia del equipo.

## 4. Decisiones implícitas por escenario

| ASR | Decisiones implícitas |
|---|---|
| **D-3** | `componente_gestor_bloqueo` es el único que bloquea sobre `bd_bloqueo`; el bloqueo vence a los 8 min; el almacén lo ejecuta en un solo hilo. |
| **L-1** | Bloqueo atómico en memoria con expiración de 8 min; persistencia asíncrona por cola (ver punto 6). |
| **E-1** | La cola es un amortiguador corto, no resuelve una carga sostenida (para eso está el escalado horizontal); la confirmación sigue siendo síncrona. |
| **S-1** | Las detecciones leen contadores desde memoria; los eventos llegan por `cola_evento_trafico`; el gateway no espera el veredicto. |
| **S-2** | Índice de qué pertenece a cada actor en memoria; limpieza definitiva de registros asíncrona; se apoya en el registro de auditoría de S-1. |
| **D-1** | Detección de excepciones (errores, rechazos de conexión y tiempos agotados en las llamadas reales de pago). |
| **D-2** | Reconfiguración hacia la pasarela sana; degradación a una sola pasarela; asiento independiente del cobro; clave de idempotencia por pago. |
| **M-1** | Restringir las dependencias (el núcleo no depende de ninguna pasarela); abstraer servicios comunes (reintentos, registro, idempotencia). |
| **M-3** | Despliegue incremental por porcentaje; reversión en ≤ 2 min; interruptores de funcionalidad; vinculación en tiempo de ejecución; motor de reglas encapsulado. |
| **I-1** | Adaptar la interfaz; un adaptador por promotor; modelo común que esconde los formatos; reglas de mapeo como datos; validación y cuarentena. |

## 5. Tácticas expuestas

Se exponen 19 tácticas, con los nombres de la documentación del curso.

| ASR | Tácticas |
|---|---|
| D-3 | Transacciones |
| L-1 | Introducir concurrencia · Caché hit / caché miss · Acotar el tamaño de colas · Reducir la sobrecarga |
| E-1 | Escalado horizontal · Encolar solicitudes · Acotar el tamaño de colas · Introducir concurrencia |
| S-1 | Detectar intrusión · Detectar denegación de servicio · Mantener un registro de auditoría |
| S-2 | Revocar el acceso · Restaurar el estado |
| D-1 | Ping / echo |
| D-2 | Redundancia activa · Reintento |
| M-1 | Encapsular · Usar un intermediario · Parametrización |
| M-3 | Parametrización |
| I-1 | Orquestación |

## 6. Supuestos, límites y puntos abiertos

**Fuera del alcance**
- Los escenarios sin priorizar (L-2, E-2, M-2 e I-2) y los subpriorizados sin experimento (D-1, D-2, M-1, M-3 e I-1).
- El control de acceso en puerta queda sin escenario experimentado.
- La disponibilidad de hardware: solo se trata la de software, en el flujo de pago.
- Resistir ataques como escenario de calidad: se maneja de forma implícita.
- El precio total único y la detección y recuperación de fallas de instancias como ASR: se manejan de forma implícita.

**Supuestos de trabajo**
- La latencia se exige en 150 ms (p95), más estricta que el 1 s del enunciado, y se mide solo en operación normal.
- La variación de impuestos por país (M-2) es una extensión del equipo; el enunciado solo menciona precios con y sin impuestos y la apertura de 2 países más.
- Las 8 horas-hombre de M-3 se eligieron para distinguir reglas como datos de reglas en el código; las 120, 40 y 8 horas-hombre no tienen línea base.
- Tarifas e impuestos: no se valida que sean legalmente correctos.

**Límites conocidos**
- **Falla sin señal (D-1).** Una pasarela que se cuelga sin responder solo se detecta al vencer el tiempo de espera. Con 150 ms ese tiempo tendría que ser tan corto que marcaría como caída una pasarela lenta pero sana.
- **Techo del bloqueo (E-1).** El bloqueo atómico corre en un único hilo y no escala: su techo es el de ese hilo (el pico pide unas 133 operaciones por segundo).
- **Primeras solicitudes de un ataque (S-1).** Pueden pasar antes de la marca, porque el gateway no espera el veredicto; S-2 se encarga de recuperar.
- **Parametrización (M-1).** Reduce las horas de configurar, desplegar y activar la pasarela, pero no elimina escribir el adaptador, que es la parte más grande de las 120 horas-hombre.

**Abierto**
- El broker de las colas (Redis o RabbitMQ) y la tecnología concreta de caché, colas y bus no están fijados.
- El documento y el diagrama siguen en revisión: los nombres de los componentes pueden cambiar.

**Por conciliar.** El documento de ASRs formula las hipótesis de L-1 y E-1 con persistencia asíncrona por cola, pero el diagrama de componentes guarda la reserva directo y de forma síncrona en `bd_reserva` (decisión clave 1). Conviene ajustar las hipótesis de los ASRs.
