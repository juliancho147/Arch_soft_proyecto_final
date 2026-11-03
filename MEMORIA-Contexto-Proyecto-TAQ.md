# Memoria de contexto — Proyecto Final TAQ (ARTI4109)

Fuente: `ARTI4109-ProyectoFinal-Grupo2-Eventos.pdf` (2 páginas).
Curso: ARTI4109 – Arquitectura de Software · Maestría en Arquitecturas de TI (MATI) · Dpto. de Ingeniería de Sistemas y Computación, Uniandes.
Proyecto: **Plataforma de Venta y Control de Acceso para Eventos en Vivo**.

## Objetivo
Diseñar la arquitectura de software del sistema e **implementar las decisiones de arquitectura** definidas para **validar el cumplimiento de los requerimientos de calidad** (experimentos / validación de ASRs).

## Grupo 2
- Carlos Santiago Benitez Malaver — cs.benitez@uniandes.edu.co
- Cristhian Yovany Almonacid Rojas — c.almonacidr@uniandes.edu.co
- Cristian Alberto Triana Villa — ca.trianav1@uniandes.edu.co
- Juan Camilo Palacios Romero — jc.palaciosr1@uniandes.edu.co

## Contexto del negocio (TAQ)
- Vende boletas de conciertos, festivales y eventos deportivos en **4 países**.
- ~**1.200 eventos/año**, **+40 promotores**, **60 recintos** aliados.
- Cada promotor envía mapa de localidades, precios y condiciones **en el formato de su propio sistema** (heterogeneidad).
- **2 pasarelas de pago** contratadas.
- Control de ingreso con lectores de códigos de **3 fabricantes** distintos.
- Incidentes previos:
  - Un promotor reportó precios **con impuestos** y otro **sin ellos**; la plataforma publicó ambos sin advertir la diferencia.
  - En la última preventa de un festival la plataforma **dejó de responder a los minutos** de abrir la venta y gran parte de las boletas terminó con **revendedores a 3x el precio**.

## Reto: nueva plataforma web y móvil de venta y control de acceso

### Carga y desempeño
- Estado normal: **400 compras/min**.
- Preventa de alta demanda: hasta **8.000 solicitudes de reserva/min** durante hasta **15 min**.
- Confirmación de reserva al elegir asiento: **< 1 s**.
- Día del evento: estadio con hasta **25.000 asistentes en 90 min** (~278/min promedio); validación de cada boleta en puerta **< 1 s**. El ingreso **no puede detenerse**.

### Consistencia de reservas
- Asiento bloqueado **8 min** para el comprador mientras paga.
- **Nunca** un mismo asiento puede venderse dos veces.

### Disponibilidad / tolerancia a fallos
- Si una pasarela de pago no responde, se reintenta por la **otra** sin que el comprador pierda el asiento.
- La falla de **cualquier servidor** no puede hacer perder reservas ni compras confirmadas (durabilidad).

### Seguridad / antifraude
- Revendedores usan: bots que envían miles de solicitudes desde muchas IPs; cuentas robadas o creadas en masa para evadir el **límite de 4 boletas por persona**; falsificación/duplicación de códigos de boletas para vender fuera de la plataforma.
- Debe **identificar y bloquear** ese tráfico **sin impedir la compra a usuarios legítimos**.
- **Ninguna boleta falsificada o ya utilizada** puede dar acceso a un recinto.

### Modificabilidad / extensibilidad
- Próximo año: **+15 promotores** nuevos y **2 países más**, cada uno con sus **pasarelas de pago locales**.
- Incorporar promotor, pasarela o fabricante de lectores **sin cambios en el núcleo de venta**.
- Poder **reemplazar una pasarela en producción sin interrumpir ventas**.

### Cambio de reglas en caliente
- Reglas de detección de bots y reglas de **precios dinámicos** (suben/bajan por demanda) se ajustan casi **cada semana**.
- Un cambio de reglas debe poder aplicarse **primero a una parte del tráfico** (canary / rollout parcial) y, si falla, **revertirse en < 2 min** sin detener una venta en curso.

## Resumen de atributos de calidad (candidatos a ASR)
| # | Atributo | Requerimiento clave |
|---|----------|---------------------|
| 1 | Desempeño / escalabilidad | 8.000 reservas/min por 15 min; confirmación < 1 s |
| 2 | Consistencia | Cero doble venta; bloqueo de 8 min |
| 3 | Disponibilidad | Failover entre pasarelas sin perder el asiento; sin pérdida de datos ante falla de servidor |
| 4 | Desempeño (acceso) | Validación en puerta < 1 s; 25.000 personas en 90 min; ingreso ininterrumpido |
| 5 | Seguridad | Bloqueo de bots/cuentas fraudulentas; tope 4 boletas/persona; boletas infalsificables, de un solo uso |
| 6 | Modificabilidad / interoperabilidad | Nuevos promotores, pasarelas y lectores sin tocar el núcleo; reemplazo de pasarela en caliente |
| 7 | Despliegue / operabilidad | Reglas con rollout parcial y rollback < 2 min sin cortar ventas |
| 8 | Integridad de datos | Normalizar formatos de promotores (p. ej. precios con/sin impuestos) y advertir diferencias |

## Notas de trabajo
- El documento no define entregables, fechas ni formato de entrega; confirmar con el curso.
- Relacionado con la skill `arch-experiment-analysis` (ASRs, hipótesis, experimentos, diagramas de despliegue/arquitectura).
