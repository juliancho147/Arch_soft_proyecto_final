# Tácticas aplicadas sobre los ASRs de TAQ

Se exponen 19 tácticas, con los nombres de la documentación del curso. Lo demás se maneja como decisión implícita de la arquitectura.

**Priorizados (en orden de importancia):** D-3, L-1, E-1 y S-1.
**Subpriorizados:** D-1, D-2, S-2, M-1, M-3 e I-1.
**Sin tácticas expuestas (sin priorizar):** L-2, E-2, M-2 e I-2.

---

## D-3 · Prevenir la doble reserva de un asiento (Priorizado, N.º 1)
**Medida:** 0 asientos con más de una reserva · **1 táctica expuesta**

| Táctica | Aplicación en D-3 |
|---|---|
| **Transacciones** | El bloqueo de los asientos es una sola operación atómica y aislada: o se bloquean todos los asientos pedidos o ninguno, y si dos solicitudes compiten por el mismo asiento solo una lo obtiene. |

**Decisiones implícitas de la arquitectura**
- componente_gestor_bloqueo es el único que ejecuta el bloqueo sobre bd_bloqueo.
- El bloqueo vence a los 8 min.
- El almacén ejecuta el bloqueo en un solo hilo; un solo hilo en todo el servicio se descartó porque rompe E-1.

**Descartada.** Introducir concurrencia no se usa aquí. En L-1 y E-1 sirve para la velocidad; para D-3 hay que serializar el bloqueo, no paralelizarlo.

---

## L-1 · Confirmar una reserva (Priorizado, N.º 2)
**Medida:** p95 ≤ 150 ms · **4 tácticas expuestas**

| Táctica | Aplicación en L-1 |
|---|---|
| **Introducir concurrencia** | Varias instancias y varios hilos atienden reservas en paralelo, sin que una espere a otra. |
| **Caché hit / caché miss** | El mapa de asientos se consulta primero en memoria: si está (hit) se responde de inmediato; si no (miss), se lee de la fuente y se guarda para la próxima. |
| **Acotar el tamaño de colas** | Se limita cuántas solicitudes pueden esperar; las que sobran se rechazan rápido para no subir la latencia de las demás. |
| **Reducir la sobrecarga** | Se quitan procesos intermedios del camino de la reserva, para llegar al destino en menos pasos. |

**Decisiones implícitas de la arquitectura**
- Bloqueo atómico en memoria con expiración de 8 min (garantiza que un asiento no se venda dos veces).
- Persistencia asíncrona por cola.

---

## E-1 · Sostener la preventa (Priorizado, N.º 3)
**Medida:** p95 < 250 ms · 8.000/min · 15 min · **4 tácticas expuestas**

| Táctica | Aplicación en E-1 |
|---|---|
| **Escalado horizontal** | Se agregan instancias del servicio de reservas a medida que sube la carga, con un balanceador que reparte las solicitudes. |
| **Encolar solicitudes** | Las solicitudes entran a una cola y las instancias las van tomando, para absorber el pico mientras la capacidad crece. |
| **Acotar el tamaño de colas** | Reutilizada de L-1. Lo que no cabe en la cola se rechaza rápido, para que la espera no supere el p95. |
| **Introducir concurrencia** | Reutilizada de L-1. Las instancias atienden en paralelo, sin estado local. |

**Condición.** El p95 de E-1 incluye el tiempo de espera en la cola. La cola es un amortiguador corto, no resuelve una carga sostenida; para eso está el escalado horizontal. La confirmación sigue siendo síncrona.

**Mencionadas, no centrales.** Caché hit / caché miss y Reducir la sobrecarga (reutilizadas de L-1).

---

## S-1 · Detectar un ataque (Priorizado, N.º 4)
**Medida:** Detección ≤ 100 ms · **3 tácticas expuestas**

| Táctica | Aplicación en S-1 |
|---|---|
| **Detectar intrusión** | Compara cada solicitud con patrones conocidos de comportamiento automatizado: firmas de bots, cadencias imposibles para un humano, recorridos repetidos. |
| **Detectar denegación de servicio** | Compara el tráfico actual con una línea base de tráfico normal: solicitudes por IP, por dispositivo y por cuenta. |
| **Mantener un registro de auditoría** | Guarda la evidencia de cada detección (IP, cuenta, hora); sirve de base para recuperarse en S-2. |

**Decisiones implícitas de la arquitectura**
- Las dos detecciones leen sus contadores desde memoria para cumplir los 100 ms.
- Los eventos de tráfico llegan por una cola (cola_evento_trafico) para no frenar la solicitud del comprador: el gateway publica y sigue, sin esperar el veredicto.

**Descartada.** Verificar la integridad de los mensajes (token firmado o desafío): ayuda más a resistir que a detectar, y resistir ataques no es un ASR.

---

## S-2 · Recuperarse de un ataque (Subpriorizado)
**Medida:** Recuperación ≤ 300 ms · **2 tácticas expuestas**

| Táctica | Aplicación en S-2 |
|---|---|
| **Revocar el acceso** | Quita el acceso a las cuentas, IP y dispositivos del actor fraudulento, para cortar el ataque y evitar que sigan comprando. |
| **Restaurar el estado** | Devuelve el inventario a su estado previo al ataque: libera los asientos retenidos y cancela las órdenes ilegítimas. |

**Decisiones implícitas de la arquitectura**
- El índice de qué pertenece a cada actor está en memoria y la limpieza definitiva de los registros se hace de forma asíncrona, para cumplir los 300 ms. Se apoya en el registro de auditoría de S-1.

**Descartadas.** Mantener un registro de auditoría (ya está en S-1) e Informar a los actores (S-1 ya alerta al equipo y avisar a compradores no entra en los 300 ms).

---

## D-1 · Detectar la falla de un componente del pago (Subpriorizado)
**Medida:** Detección < 150 ms · **1 táctica expuesta**

| Táctica | Aplicación en D-1 |
|---|---|
| **Ping / echo** | El orquestador envía una consulta de prueba al componente de pago y espera la respuesta; si no llega, lo marca como no disponible. |

**Decisiones implícitas de la arquitectura**
- Detección de excepciones: se capturan errores, rechazos de conexión y tiempos agotados en las llamadas reales de pago.

**Descartadas.** Heartbeat (la pasarela es un servicio externo y no emite señales) y Monitor (queda como parte natural de la arquitectura).

**Límite.** Una caída sin ninguna señal, en la que la pasarela se cuelga sin responder, solo se detecta cuando vence el tiempo de espera. Con 150 ms ese tiempo tendría que ser muy corto y marcaría como caída una pasarela lenta pero sana.

---

## D-2 · Recuperarse de la falla de un componente del pago (Subpriorizado)
**Medida:** Recuperación ≤ 300 ms · **2 tácticas expuestas**

| Táctica | Aplicación en D-2 |
|---|---|
| **Redundancia activa** | Las dos pasarelas están activas y listas al mismo tiempo, por lo que pasar a la otra es inmediato. |
| **Reintento** | Si un pago falla, se vuelve a intentar por la otra pasarela, lo que completa el cobro. |

**Decisiones implícitas de la arquitectura**
- Reconfiguración: se reasigna el flujo de pagos hacia la pasarela sana.
- Degradación: se sigue operando con una sola pasarela mientras la otra se recupera.
- El asiento reservado es independiente del cobro, para no perderse.
- Cada pago lleva una clave de idempotencia, para no cobrar dos veces.

**Descartada.** Redundancia pasiva: su conmutación más lenta pondría en riesgo los 300 ms.

---

## M-1 · Incorporar una pasarela de pago nueva (Subpriorizado)
**Medida:** ≤ 120 horas-hombre · **3 tácticas expuestas**

| Táctica | Aplicación en M-1 |
|---|---|
| **Encapsular** | Una interfaz estable de pagos esconde cómo trabaja cada pasarela; el núcleo solo conoce la interfaz. |
| **Usar un intermediario** | Un adaptador por pasarela traduce su protocolo a la interfaz común; una pasarela nueva es un adaptador nuevo. |
| **Parametrización** | La dirección, las credenciales, las opciones y la activación de cada pasarela son parámetros y no código; el adaptador se registra por configuración. |

**Decisiones implícitas de la arquitectura**
- Restringir las dependencias: el núcleo de venta no depende directamente de ninguna pasarela.
- Abstraer servicios comunes: reintentos, registro e idempotencia viven en un solo lugar, para que el adaptador nuevo solo escriba lo específico.

**Alcance de la parametrización.** Reduce las horas de configurar, desplegar y activar la pasarela, pero no elimina escribir el adaptador, que es la parte más grande de las 120 horas-hombre. Se parametriza solo lo que probablemente cambie.

**Reutilización.** La parametrización también aplica a M-3.

---

## M-3 · Cambiar reglas de forma gradual y reversible (Subpriorizado)
**Medida:** ≤ 8 h-h · reversión ≤ 2 min · **1 táctica expuesta**

| Táctica | Aplicación en M-3 |
|---|---|
| **Parametrización** | Reutilizada de M-1. Las reglas de detección y de precios son datos versionados y no código; modificar una regla es cambiar un dato. |

**Decisiones implícitas de la arquitectura**
- Despliegue incremental: la regla nueva se aplica primero a un porcentaje del tráfico y se va ampliando.
- Reversión: se vuelve a la versión anterior de la regla en ≤ 2 min.
- Interruptores de funcionalidad: cada regla se activa o desactiva con un interruptor.
- Vinculación en tiempo de ejecución: las reglas se cargan sin reiniciar, para no detener ventas en curso.
- Encapsular: el motor de reglas es un componente aislado.

---

## I-1 · Interpretar los formatos de los promotores (Subpriorizado)
**Medida:** 100 % válidos · 100 % inválidos apartados · **1 táctica expuesta**

| Táctica | Aplicación en I-1 |
|---|---|
| **Orquestación** | Un coordinador central dirige los pasos en orden (recibir, validar, normalizar y publicar o apartar), de modo que ningún registro se publica sin validarse y cada registro deja rastro de lo que pasó con él. |

**Decisiones implícitas de la arquitectura**
- Adaptar la interfaz: se traduce el formato de cada promotor al modelo común (campos, tipos, precios con o sin impuestos).
- Usar un intermediario: un adaptador por promotor.
- Encapsular: el modelo común esconde los formatos de origen.
- Parametrización: las reglas de mapeo y validación son datos.
- Validación de cada registro y cuarentena de los inválidos, para no perder datos.

**Por qué orquestación y no coreografía.** La medida de I-1 es estricta (100 % de válidos interpretados, 100 % de inválidos apartados, sin pérdida de datos). Con un coordinador central es más sencillo asegurar y comprobar ese resultado de punta a punta. La coreografía queda fuera, como decisión implícita.

---

## Resumen: tácticas expuestas y ASRs que atacan

| # | Táctica expuesta | ASRs que ataca | También interviene |
|---|---|---|---|
| 1 | Introducir concurrencia | L-1, E-1 | |
| 2 | Caché hit / caché miss | L-1 | E-1 (mencionada) |
| 3 | Acotar el tamaño de colas | L-1, E-1 | |
| 4 | Reducir la sobrecarga | L-1 | E-1 (mencionada) |
| 5 | Escalado horizontal | E-1 | |
| 6 | Encolar solicitudes | E-1 | |
| 7 | Detectar intrusión | S-1 | |
| 8 | Detectar denegación de servicio | S-1 | |
| 9 | Mantener un registro de auditoría | S-1 | S-2 (implícito) |
| 10 | Revocar el acceso | S-2 | |
| 11 | Restaurar el estado | S-2 | |
| 12 | Ping / echo | D-1 | |
| 13 | Redundancia activa | D-2 | |
| 14 | Reintento | D-2 | |
| 15 | Encapsular | M-1 | M-3, I-1 (implícito) |
| 16 | Usar un intermediario | M-1 | I-1 (implícito) |
| 17 | Parametrización | M-1, M-3 | I-1 (implícito) |
| 18 | Orquestación | I-1 | D-2 (implícito, en el orquestador de pagos) |
| 19 | Transacciones | D-3 | |

Para interoperabilidad, la lista del curso solo tiene Orquestación y Coreografía; se eligió Orquestación y la coreografía queda como decisión implícita. D-3, el escenario priorizado número 1, expone Transacciones.
