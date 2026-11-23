# ASRs de TAQ — Escenarios de calidad

Cada escenario va desde la fuente del estímulo hasta la medida de respuesta.

## Latencia

### L-1 · Confirmar una reserva

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Comprador desde la app web o móvil. |
| Estímulo | Solicita reservar un asiento de un evento. |
| Patrón del estímulo | Carga constante de 400 compras/min. |
| Artefacto | Servicio de reservas e inventario de asientos. |
| Entorno | Operación normal, sin picos ni fallas inyectadas. |
| Respuesta | La plataforma confirma la reserva y bloquea el asiento para ese comprador durante 8 min. |
| Medida de respuesta | **p95 ≤ 150 ms** |

### L-2 · Validar una boleta en puerta

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Asistente que presenta su boleta en un lector de puerta, de cualquiera de los 3 fabricantes. |
| Estímulo | Solicita ingresar al recinto con el código de su boleta. |
| Patrón del estímulo | Carga constante de 300 validaciones/min. |
| Artefacto | Servicio de validación de acceso. |
| Entorno | Día del evento, operación normal, sin picos ni fallas inyectadas. |
| Respuesta | El servicio verifica la autenticidad de la boleta, comprueba que no se haya usado, la marca como usada y responde si permite o niega el ingreso. |
| Medida de respuesta | **p95 ≤ 150 ms** |

## Escalabilidad

### E-1 · Sostener la preventa

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Compradores desde la app web o móvil. |
| Estímulo | Solicitan reservar asientos de un evento de alta demanda al abrir la preventa. |
| Patrón del estímulo | Aumento súbito de 400 a 8.000 solicitudes de reserva/min, sostenido durante 15 min. |
| Artefacto | Servicio de reservas e inventario de asientos. |
| Entorno | Alta demanda con 8.000 transacciones por minuto. |
| Respuesta | La plataforma aumenta su capacidad, atiende todas las solicitudes y confirma las reservas. |
| Medida de respuesta | **p95 < 250 ms durante 15 min** |

### E-2 · Sostener los pagos en preventa

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Compradores desde la app web o móvil. |
| Estímulo | Confirman el pago de los asientos que reservaron. |
| Patrón del estímulo | Aumento súbito de 400 a 8.000 pagos/min, sostenido durante 15 min. |
| Artefacto | Orquestador de pagos. |
| Entorno | Alta demanda con 8.000 transacciones por minuto. |
| Respuesta | La plataforma aumenta su capacidad, procesa el pago a través de la pasarela y confirma la compra. |
| Medida de respuesta | **p95 < 250 ms durante 15 min** |

## Seguridad

### S-1 · Detectar un ataque

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Organizaciones de reventa, con bots y cuentas fraudulentas. |
| Estímulo | Lanzan un ataque coordinado de solicitudes automatizadas. |
| Patrón del estímulo | Durante la operación normal y durante la hora pico de una preventa. |
| Artefacto | Monitoreo de tráfico y motor antifraude. |
| Entorno | Operación normal (400 transacciones/min) y alta demanda (8.000 transacciones/min). |
| Respuesta | Identifica el patrón de ataque, alerta al equipo de operaciones y registra la evidencia (IP, cuentas, horarios). |
| Medida de respuesta | **Detección en ≤ 100 ms** |

### S-2 · Recuperarse de un ataque

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Motor antifraude, tras la alerta de S-1. |
| Estímulo | Un ataque ya detectado ha dejado asientos retenidos, órdenes y cuentas fraudulentas. |
| Patrón del estímulo | Durante la operación normal y durante la hora pico de una preventa. |
| Artefacto | Inventario de asientos, motor de reglas y gestión de cuentas. |
| Entorno | Operación normal (400 transacciones/min) y alta demanda (8.000 transacciones/min). |
| Respuesta | Libera los asientos retenidos por los actores fraudulentos, cancela sus órdenes, bloquea sus cuentas y sigue atendiendo a los demás compradores. |
| Medida de respuesta | **Recuperación en ≤ 300 ms** |

## Disponibilidad

### D-1 · Detectar la falla de un componente del pago

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Un componente del flujo de pago: la pasarela de pago u otro servicio que participa en el cobro. |
| Estímulo | Deja de responder. |
| Patrón del estímulo | Durante la operación normal. |
| Artefacto | Orquestador de pagos y su monitoreo. |
| Entorno | Operación normal (400 transacciones/min). |
| Respuesta | Detecta la falla, marca el componente como no disponible y registra y avisa del evento. |
| Medida de respuesta | **Detección en < 150 ms** |

### D-2 · Recuperarse de la falla de un componente del pago

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Orquestador de pagos, tras la detección de D-1. |
| Estímulo | Una pasarela de pago queda marcada como no disponible mientras un comprador está pagando. |
| Patrón del estímulo | Durante la operación normal. |
| Artefacto | Orquestador de pagos. |
| Entorno | Operación normal (400 transacciones/min). |
| Respuesta | Redirige el pago a la otra pasarela, conserva el asiento reservado y reintenta el cobro sin duplicarlo. |
| Medida de respuesta | **Recuperación en ≤ 300 ms** |

### D-3 · Prevenir la doble reserva de un asiento

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Compradores desde la app web o móvil. |
| Estímulo | Dos o más solicitudes llegan al mismo tiempo (en el mismo milisegundo) para un mismo grupo de asientos, o para al menos un asiento de ese grupo. |
| Patrón del estímulo | Solicitudes simultáneas sobre los mismos asientos, durante la operación normal. |
| Artefacto | Servicio de reservas e inventario de asientos. |
| Entorno | Operación normal (400 transacciones/min). |
| Respuesta | Asigna cada asiento a una sola solicitud y rechaza a las demás indicando que el asiento no está disponible. |
| Medida de respuesta | **0 asientos con más de una reserva** |

## Modificabilidad

### M-1 · Incorporar una pasarela de pago nueva

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Gerencia de TAQ. |
| Estímulo | Solicita la incorporación de un nuevo motor de pago (una pasarela de pago nueva). |
| Patrón del estímulo | Cada vez que se abre operación en un país nuevo con su propia pasarela local (2 países más el próximo año). |
| Artefacto | Capa de integración de pagos y núcleo de venta. |
| Entorno | Desarrollo de la plataforma. |
| Respuesta | Se integra la pasarela nueva con toda su configuración, sin modificar los demás componentes ni otros servicios ya montados previamente. |
| Medida de respuesta | **≤ 120 horas-hombre** |

### M-2 · Modificar la lógica de impuestos de un país

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Gerencia de TAQ. |
| Estímulo | Solicita modificar o agregar la forma de calcular los impuestos de un país. |
| Patrón del estímulo | Cada vez que se abre operación en un país nuevo (2 más el próximo año) o cambia la normativa tributaria de un país. |
| Artefacto | Componente de cálculo de impuestos. |
| Entorno | Desarrollo de la plataforma. |
| Respuesta | Se modifica o se agrega la lógica de impuestos de ese país sin modificar otros servicios ya montados previamente, ni las reglas de los otros países. |
| Medida de respuesta | **≤ 40 horas-hombre** |

### M-3 · Cambiar reglas de forma gradual y reversible

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Gerencia de TAQ. |
| Estímulo | Solicita cambiar las reglas de detección de compradores automatizados o las reglas de precios. |
| Patrón del estímulo | Casi cada semana. |
| Artefacto | Motor de reglas. |
| Entorno | Desarrollo de la plataforma para modificar las reglas, y producción con ventas en curso, en operación normal (400 transacciones/min), para aplicarlas y revertirlas. |
| Respuesta | Se modifican las reglas, se aplican primero a una parte del tráfico y, si causan problemas, se revierten sin detener ninguna venta en curso. |
| Medida de respuesta | **Modificación de las reglas en ≤ 8 horas-hombre y reversión en ≤ 2 min** |

## Interoperabilidad

### I-1 · Interpretar los formatos de los promotores

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Promotor de eventos. |
| Estímulo | Envía el mapa de localidades, los precios y las condiciones de un evento en el formato de su propio sistema, con precios que pueden incluir o no los impuestos. |
| Patrón del estímulo | Cada vez que un promotor publica o actualiza un evento (unos 1.200 eventos al año, de más de 40 promotores). |
| Artefacto | Módulo de ingesta y normalización. |
| Entorno | Operación normal. |
| Respuesta | Convierte los registros válidos a un modelo común, identificando si el precio incluye impuestos, y aparta los registros inválidos con el motivo, para que no se publiquen. |
| Medida de respuesta | **100 % de los registros válidos interpretados correctamente y 100 % de los registros inválidos apartados, sin pérdida de datos** |

### I-2 · Interpretar las lecturas de lectores de distintos fabricantes

| Elemento | Descripción |
|---|---|
| Fuente del estímulo | Lectores de códigos de 3 fabricantes diferentes, en la puerta del recinto. |
| Estímulo | Envían la lectura de una boleta, cada uno en su propio protocolo y formato. |
| Patrón del estímulo | Cada vez que un asistente presenta su boleta el día del evento. |
| Artefacto | Capa de integración con lectores y servicio de validación de acceso. |
| Entorno | Día del evento, operación normal (300 validaciones/min). |
| Respuesta | Traduce cada lectura a un mensaje común, valida la boleta y devuelve la respuesta en el formato que espera cada fabricante. |
| Medida de respuesta | **100 % de las lecturas válidas interpretadas correctamente y 100 % de las lecturas inválidas rechazadas, sin pérdida de datos** |
