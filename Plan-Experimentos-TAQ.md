# Plan de experimentación — Plataforma TAQ (ARTI4109, Grupo 2)

Documento de trabajo. Cada experimento se agrega solo después de que el equipo lo aprueba.
ASRs: ver `ASRs-TAQ.md`. Tácticas: ver `Tacticas-TAQ.md`. Arquitectura: `Arquitectura-TAQ.drawio`.

## Decisiones generales

- **Herramientas:** JMeter genera la carga y Prometheus mide la métrica real de cada ASR dentro de la plataforma.
- **Entorno:** Kubernetes local con minikube, con posibilidad de pasar a AWS EKS. Son los mismos manifiestos.
- **Pasarelas de pago:** simuladas, con latencia fija y fallas inyectables.
- **Frontera de medición:** JMeter mide desde el cliente (incluye red local y kube-proxy). El ASR se mide desde que la solicitud entra al `componente_api_gateway`, con Prometheus. Siempre se documenta la diferencia entre las dos cifras.

## Experimentos

| Experimento | ASRs | Tipo | Qué se prueba | Estado |
|---|---|---|---|---|
| EXP-1 | L-1, E-1 | Código | Carga constante y rampa a 8.000/min | aprobado |
| EXP-2 | S-1, S-2 | Código | Simular un ataque y medir detección y recuperación | aprobado |
| EXP-3 | D-1, D-2 | Código | Inyectar fallas en la pasarela simulada | aprobado |
| EXP-4 | I-1, M-1, M-3 | Encuesta | Arquitecto externo, que valida interoperabilidad y modificabilidad | tipo definido; contenido por definir |

---

## EXP-1 — Latencia y escalabilidad de reservas (L-1 y E-1)  ✅ aprobado

**Hipótesis**

- **L-1:** si se aplican *Introducir concurrencia*, *Caché hit / caché miss*, *Acotar el tamaño de colas* y *Reducir la sobrecarga*, entonces el p95 de confirmación será ≤ 150 ms a 400 compras/min con una sola réplica.
- **E-1:** si se aplican *Escalado horizontal* (manual, de 1 a ≤ 8 réplicas), *Encolar solicitudes*, *Acotar el tamaño de colas* e *Introducir concurrencia*, entonces el p95 será < 250 ms a 8.000/min durante 15 min.

**Fases**

| Fase | Réplicas | Carga | Duración |
|---|---|---|---|
| A (L-1) | 1 fija | 400/min constante | 10 min, más 1 min de calentamiento |
| B (E-1) | Empieza en 1 y escala con la orden a N ≤ 8 | Rampa de 400 a 8.000/min | 15 min sostenidos |

**Cómo se elige N:** se repite la fase B con N = 2, 4 y 8. El experimento se cumple si alguna N ≤ 8 logra el p95 < 250 ms; el resultado es la N mínima que lo logra. La orden se da con `kubectl scale` al iniciar la rampa.

**Qué escala:** `componente_reserva` y `componente_api_gateway`, los dos nodos con ×N en el camino de la reserva (supuesto por confirmar).

**Asientos:** el evento de prueba lleva unos 130.000 asientos, para que todas las solicitudes puedan confirmarse y no se mida el rechazo por falta de asientos.

**Qué se mide**

- Prometheus: histograma desde que la solicitud entra al gateway hasta que sale la confirmación. El p95 principal se calcula sobre los 15 min completos, incluyendo la ventana de arranque de las réplicas nuevas.
- Dato adicional: p95 solo después de que las réplicas están listas, y cuánto tardaron en arrancar.
- JMeter: p95 desde el cliente; se documenta la diferencia con Prometheus.
- También: errores, CPU y memoria por réplica.

**Criterio de éxito:** p95 < 250 ms sobre los 15 min en alguna N ≤ 8, con 0 errores atribuibles a la plataforma.

**Qué NO valida:** el autoescalado automático (solo prueba que, si se escala a tiempo, la plataforma cumple); más de 8 réplicas; las fallas (EXP-3); el rendimiento en EKS, porque minikube corre en una sola máquina y 8 réplicas más las colas y los almacenes compiten por sus recursos. Se registran las características de la máquina para interpretar el resultado.

**Palanca si falla:** si el p95 se rompe solo por la ventana de arranque, se puede dar la orden unos minutos antes de la rampa (pre-escalado) y se documenta.

---

## EXP-2 — Seguridad: detectar y recuperarse de un ataque (S-1 y S-2)  ✅ aprobado

**Hipótesis**

- **S-1:** si el `componente_api_gateway` publica cada solicitud como evento en `cola_evento_trafico` y `componente_deteccion_ataque` las evalúa de forma asíncrona, con *Detectar intrusión*, *Detectar denegación de servicio* y *Mantener un registro de auditoría*, entonces el ataque se detecta en ≤ 100 ms desde que el evento llega al detector.
- **S-2:** si `componente_respuesta_ataque` aplica *Revocar el acceso* y *Restaurar el estado* con un índice en memoria, entonces la plataforma se recupera en ≤ 300 ms.

**Cómo se define el ataque:** por el comportamiento de cada actor, no por el volumen total, porque la plataforma no sabe si está en un pico y la detección no puede depender de eso.

- 100 IP simuladas con una cabecera distinta por hilo de JMeter, de unas 10 solicitudes/min cada una (1.000/min en total).
- Los bots reservan asientos para retenerlos: unos 100 asientos retenidos al momento de la recuperación.
- Un comprador legítimo envía muchas menos solicitudes por minuto que un bot; eso es lo que distingue a uno de otro, tanto en operación normal como en un pico.
- Los valores del ataque son supuestos del equipo; el enunciado no los da.

**Escenarios.** La carga legítima de fondo es la variable que distingue normal de pico. Los picos pueden ser aleatorios, así que en cada incidente el ataque se inyecta en un instante aleatorio dentro de la ventana de la prueba.

| Escenario | Plataforma | Tráfico legítimo de fondo | Incidentes |
|---|---|---|---|
| A. Operación normal | 1 réplica fija | 400 compras/min | 30 |
| B. Hora pico | Con la N de réplicas que cumplió EXP-1 | 8.000/min | 10 |

**Qué se mide**

- **S-1:** tiempo entre que el evento entra al detector y que queda registrada la evidencia en `bd_auditoria`, como histograma en Prometheus.
- **S-2:** tiempo desde la alerta del detector hasta que los asientos retenidos están liberados, las órdenes canceladas y las cuentas revocadas, medido con un script que consulta el estado cada pocos milisegundos.
- **Datos adicionales:** cuántas solicitudes fraudulentas pasaron antes de la marca (efecto de que la detección sea asíncrona); el p95 del tráfico legítimo durante la recuperación.
- **Solo en el escenario B:** la profundidad máxima de `cola_evento_trafico` (si el detector acumula retraso) y cuántos compradores legítimos fueron marcados como sospechosos (se espera 0).

**Criterio de éxito:** p95 de detección ≤ 100 ms y p95 de recuperación ≤ 300 ms, en los dos escenarios.

**Qué NO valida:** resistir ataques (no es un ASR); bots sofisticados que imiten a un humano; ataques volumétricos de red; un reparto real de IP en internet, porque las IP se simulan con cabeceras; el rendimiento en EKS.

---

## EXP-3 — Disponibilidad de pagos: detectar y recuperarse de la falla de una pasarela (D-1 y D-2)  ✅ aprobado

**Hipótesis**

- **D-1:** si `componente_verificador_salud` aplica *Ping / echo* sobre el grupo de pasarelas, apoyado en la detección de excepciones (decisión implícita), entonces la caída de una pasarela se detecta en menos de 150 ms.
- **D-2:** si `componente_grupo_pasarela` mantiene las dos pasarelas activas (*Redundancia activa*) y `componente_orquestador_pago` aplica *Reintento* con la misma clave de idempotencia, entonces el pago se recupera por la otra pasarela en ≤ 300 ms, sin perder el asiento ni cobrar dos veces.

**Escenario, solo operación normal**

- 400 compras/min con una réplica fija.
- Una de las dos pasarelas simuladas falla en un instante aleatorio de la ventana, igual que en EXP-2.
- Dos tipos de falla, 15 incidentes de cada uno (30 en total):
  1. **Cuelgue:** la pasarela deja de responder.
  2. **Error inmediato:** la pasarela rechaza la conexión.

**Qué se mide**

- **D-1:** el simulador anota el instante en que empieza a fallar; se mide hasta que el orquestador marca esa pasarela como no disponible.
- **D-2:** desde esa marca hasta que el primer reintento llega a la pasarela B simulada.
- **Condiciones de aceptación:** 0 asientos perdidos (los asientos de los pagos afectados siguen reservados y el pago termina confirmado) y 0 cobros duplicados (cada clave de idempotencia aprobada aparece una sola vez en el simulador).
- **Datos adicionales:** pagos en vuelo al momento de la falla y tiempo total del pago afectado.

**Parámetro supuesto:** el verificador sondea cada 50 ms con un tiempo límite de 50 ms, de modo que el cuelgue se detecte en unos 100 ms en el peor caso. Es un supuesto del equipo.

**Criterio de éxito:** p95 de detección < 150 ms y p95 de recuperación ≤ 300 ms, con 0 asientos perdidos y 0 cobros duplicados.

**Qué NO valida:** las respuestas con valor incorrecto (el experimento solo mira si la pasarela está viva o caída); la caída simultánea de las dos pasarelas; la hora pico; pasarelas reales, que pueden tardar más de 150 ms en un pago normal; las fallas de instancias de los servicios; el reemplazo planificado de una pasarela.

---

## EXP-4 — Encuesta a un arquitecto externo: interoperabilidad y modificabilidad (I-1, M-1 y M-3)

**Decisión:** la interoperabilidad (I-1) y la modificabilidad (M-1 y M-3) se validan con una **encuesta a un arquitecto externo al proyecto**, y no con pruebas de código. Los ASRs de interoperabilidad que no son prioritarios (I-2) y de modificabilidad (M-2) también quedan como encuesta.

**Tácticas que la encuesta debe permitir juzgar**

- I-1: *Orquestación*.
- M-1: *Encapsular*, *Usar un intermediario* y *Parametrización*.
- M-3: *Parametrización*.

**Estado:** el contenido de la encuesta (preguntas, material que recibe el evaluador, número de evaluadores y criterio de éxito) **se define más adelante**. Hay un borrador de ideas en la conversación de diseño, no aprobado.
