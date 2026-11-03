# Plataforma TAQ — Venta y control de acceso para eventos en vivo

Proyecto Final de **ARTI4109 – Arquitectura de Software** · Maestría en Arquitecturas de TI (MATI) · Universidad de los Andes · **Grupo 2**.

Este repositorio contiene el diseño de arquitectura de una plataforma web y móvil para que la compañía TAQ venda boletas de conciertos, festivales y eventos deportivos y controle el ingreso a los recintos, junto con el plan para validar con experimentos que la arquitectura cumple sus requerimientos de calidad.

## Empezar por aquí

Abra **[`index.html`](index.html)** en cualquier navegador. Es el documento único del proyecto: no necesita servidor ni instalación, y los diagramas van incrustados.

- **Modo lectura:** documento continuo con índice lateral.
- **Modo diapositivas:** botón "▶ Modo diapositivas", flechas ← →, `Esc` para salir. También se abre con `index.html?modo=diapositivas`.

Si prefiere leer en Markdown, siga la tabla de la siguiente sección.

## El problema en breve

| Tema | Dato clave |
|---|---|
| Negocio | 4 países, ~1.200 eventos/año, +40 promotores, 60 recintos, 2 pasarelas de pago, lectores de 3 fabricantes |
| Carga normal | 400 compras/min |
| Preventa | hasta 8.000 reservas/min durante 15 min; confirmación < 1 s |
| Consistencia | asiento bloqueado 8 min; nunca se vende dos veces |
| Disponibilidad | failover entre pasarelas sin perder el asiento; ninguna falla de servidor pierde reservas confirmadas |
| Control de acceso | 25.000 asistentes en 90 min; validación en puerta < 1 s |
| Antifraude | bloquear bots y cuentas falsas (tope de 4 boletas por persona) sin afectar a compradores legítimos |
| Cambio de reglas | rollout parcial y rollback en < 2 min sin detener una venta |

Resumen completo del enunciado: [`MEMORIA-Contexto-Proyecto-TAQ.md`](MEMORIA-Contexto-Proyecto-TAQ.md). Fuente original: [`ARTI4109-ProyectoFinal-Grupo2-Eventos.pdf`](ARTI4109-ProyectoFinal-Grupo2-Eventos.pdf).

## Contenido del repositorio

```
.
├── index.html                                  Documento completo (lectura + diapositivas)
├── README.md                                   Esta guía
├── MEMORIA-Contexto-Proyecto-TAQ.md            Resumen del enunciado
├── ASRs-TAQ.md                                 Etapa 1: requerimientos de calidad (13 ASRs)
├── ASRs-TAQ.xlsx                               ASRs en hoja de cálculo para el Product Manager
├── ASRs-TAQ_Revisado.xlsx                      Versión revisada de la hoja de ASRs
├── Tacticas-TAQ.md                             Etapa 2: tácticas de arquitectura por ASR
├── Arquitectura-TAQ.drawio                     Etapa 3: arquitectura (6 diagramas, uno por página)
├── Diagramas SVG/                              Diagramas exportados
│   ├── 1-componentes.svg
│   ├── 2-secuencia-reserva.svg
│   ├── 3-secuencia-pago-falla.svg
│   ├── 4-despliegue.svg
│   ├── 5-desarrollo.svg
│   └── 6-informacion.svg
├── Plan-Experimentos-TAQ.md                    Etapa 4: plan de experimentación
└── ARTI4109-ProyectoFinal-Grupo2-Eventos.pdf   Enunciado original
```

## Cómo se construyó: etapas del trabajo

| Etapa | Documento | Qué contiene | Estado |
|---|---|---|---|
| 1. Requerimientos | [`ASRs-TAQ.md`](ASRs-TAQ.md) | 13 ASRs en 6 atributos: latencia, escalabilidad, seguridad, disponibilidad, modificabilidad, interoperabilidad | Aprobado |
| 2. Tácticas | [`Tacticas-TAQ.md`](Tacticas-TAQ.md) | 18 tácticas expuestas para los 9 ASRs priorizados | Aprobado |
| 3. Arquitectura | [`Arquitectura-TAQ.drawio`](Arquitectura-TAQ.drawio) y [`Diagramas SVG/`](Diagramas%20SVG) | Vistas funcional, concurrencia, despliegue, desarrollo e información | Dibujada |
| 4. Experimentación | [`Plan-Experimentos-TAQ.md`](Plan-Experimentos-TAQ.md) | EXP-1 a EXP-3 (código) y EXP-4 (encuesta a arquitecto externo) | Plan en curso; contenido de EXP-4 por definir |

### ASRs

| Atributo | IDs | Priorizados para experimentar |
|---|---|---|
| Latencia | L-1, L-2 | L-1 (L-2 es opcional y solo si sobra tiempo) |
| Escalabilidad | E-1, E-2 | E-1 |
| Seguridad | S-1 (detectar), S-2 (recuperarse) | S-1, S-2 |
| Disponibilidad | D-1 (detectar falla en pagos), D-2 (recuperarse) | D-1, D-2 |
| Modificabilidad | M-1, M-2, M-3 | M-1, M-3 |
| Interoperabilidad | I-1, I-2 | I-1 |

Se priorizaron 9 de los 13 ASRs. El umbral de latencia es **150 ms en p95** (más estricto que el 1 s del enunciado; decisión del equipo). Las decisiones de alcance están al inicio de [`ASRs-TAQ.md`](ASRs-TAQ.md).

### Vistas de arquitectura

Notación UML 2.0, lectura de izquierda a derecha, cada relación marcada «sync» o «async».

| # | Diagrama | Archivo |
|---|---|---|
| 1 | Componentes (vista funcional) | [`1-componentes.svg`](Diagramas%20SVG/1-componentes.svg) |
| 2 | Secuencia de una reserva | [`2-secuencia-reserva.svg`](Diagramas%20SVG/2-secuencia-reserva.svg) |
| 3 | Secuencia de un pago con falla de pasarela | [`3-secuencia-pago-falla.svg`](Diagramas%20SVG/3-secuencia-pago-falla.svg) |
| 4 | Despliegue (un cluster AWS EKS) | [`4-despliegue.svg`](Diagramas%20SVG/4-despliegue.svg) |
| 5 | Desarrollo (paquetes) | [`5-desarrollo.svg`](Diagramas%20SVG/5-desarrollo.svg) |
| 6 | Información (diagrama de clases) | [`6-informacion.svg`](Diagramas%20SVG/6-informacion.svg) |

Decisiones principales: la reserva se escribe directo y de forma síncrona en la base de datos; la detección de ataques es asíncrona, vía una cola de eventos de tráfico, y no frena la reserva; la entrada es un API Gateway; se desarrolla en local y se despliega en EKS.

### Experimentos

| Experimento | ASRs | Tipo | Qué prueba |
|---|---|---|---|
| EXP-1 | L-1, E-1 | Código | Carga constante (400/min) y rampa hasta 8.000/min |
| EXP-2 | S-1, S-2 | Código | Simular un ataque y medir detección y recuperación |
| EXP-3 | D-1, D-2 | Código | Inyectar fallas (cuelgue y error inmediato) en la pasarela simulada |
| EXP-4 | I-1, M-1, M-3 | Encuesta | Un arquitecto externo valida interoperabilidad y modificabilidad |

Herramientas: JMeter para generar carga y Prometheus para medir. Entorno: Kubernetes local con minikube, con los mismos manifiestos para pasar a AWS EKS. Las pasarelas de pago son simuladas, con latencia fija y fallas inyectables.

## Cómo ver y editar los archivos

| Archivo | Cómo abrirlo |
|---|---|
| `index.html` | Cualquier navegador |
| `*.md` | Cualquier editor o el visor de GitHub |
| `Arquitectura-TAQ.drawio` | [draw.io](https://app.diagrams.net) o la extensión *Draw.io Integration* de VS Code |
| `*.svg` | Navegador o editor de imágenes vectoriales |
| `*.xlsx` | Excel, LibreOffice o Google Sheets |

Notas para quien edite:

- Los SVG de `Diagramas SVG/` están **incrustados en base64 dentro de `index.html`**. Si cambia un diagrama, hay que regenerar el HTML; el script generador no vive en este repositorio.
- Cada ASR, táctica y experimento se agrega a su documento solo después de que el equipo lo aprueba.
- Al avanzar el plan o ejecutar experimentos, actualice también las secciones de experimentos y resultados de `index.html`.

## Equipo — Grupo 2

- Carlos Santiago Benitez Malaver
- Cristhian Yovany Almonacid Rojas
- Cristian Alberto Triana Villa
- Juan Camilo Palacios Romero

## Estado actual

Etapas 1 y 2 terminadas; arquitectura dibujada; experimentación en curso (EXP-1 a EXP-3 aprobados, EXP-4 por definir). Todavía no hay código ni resultados de experimentos en el repositorio.
