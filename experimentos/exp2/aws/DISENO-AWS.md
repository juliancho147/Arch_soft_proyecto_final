# EXP-2 en AWS (EKS): diseño de despliegue

Estado: **diseñado y preparado, nada desplegado**. No se crea ningún recurso en AWS hasta recibir el ok explícito.
Lo local (cluster `taq` de kind y panel) está apagado.

## 1. Por qué AWS
En el Mac (Docker con 7,8 GiB) no caben 8 réplicas de `nodo_entrada` y `nodo_reserva` más monitoreo, datos y generador de carga.
El plan de EXP-2 ya contemplaba EKS con autoescalado de pods y de nodos.

## 2. Arquitectura

```
                    ┌──────────── EKS "taq-exp" (us-east-1, nodos en 1 sola zona) ────────────┐
 tu equipo          │  nodos "carga"  (1 × c7g.xlarge, aislado por taint)                      │
 ┌────────────┐     │    · jmeter  ── 8.000/min ──┐         · panel de inyección (:8088)       │
 │ navegador  │     │                             ▼                                            │
 │ kubectl    │◄────┤  nodos "app" (2→6 × m7g.xlarge, autoescalado de nodos)                   │
 │ port-forward│    │    nodo-entrada ×1..8 ─► Redis (colas) ─► nodo-reserva ×1..8             │
 └────────────┘     │         (HPA 60 % CPU)                      (HPA 60 % CPU)  ─► pasarela ×1..8
   Grafana :30300   │                                   │ operaciones                          │
   Panel   :8088    │  nodos "sistema" (2 × m7g.large, fijos)    ▼                             │
   Prom    :30900   │    bd-bloqueo ×1 (hilo único) · Redis · PostgreSQL (130.000 asientos)    │
                    │    Prometheus · Grafana · kube-state-metrics · node-exporter             │
                    └──────────────────────────────────────────────────────────────────────────┘
```

| Decisión | Elección | Razón |
|---|---|---|
| Región / zona | us-east-1; nodos en una sola zona (1a) | Menor costo y sin tráfico entre zonas. El plano de control exige 2 zonas, y eksctl las crea. |
| Arquitectura de CPU | Graviton (arm64) | La imagen que ya construimos en el Mac es arm64; es más barato que x86. |
| Red | Nodos en subred pública, sin NAT Gateway, grupos de seguridad cerrados | Evita ~USD 0,045/h + datos del NAT. Nada queda expuesto: se entra con `port-forward`. |
| Monitoreo | `kube-prometheus-stack` (Prometheus + Grafana) dentro del clúster | Ya previsto en el plan. Agrega réplicas por pod (kube-state-metrics) y CPU/memoria por réplica (cAdvisor). |
| Conexión al "ambiente de monitoreo que tenemos" | Mismo Grafana, mismos paneles de EXP-1, uid de datasource `prom`; un `PodMonitor` descubre cada réplica | El scrape estático de local no sirve con N réplicas. |
| Autoescalado de pods | HPA en `nodo-entrada`, `nodo-reserva`, `nodo-pasarela`: 1–8 réplicas, objetivo CPU 60 %, sube rápido (hasta 4 pods o 100 % cada 15 s) y baja lento (5 min) | Como pide el plan. `bd-bloqueo` no escala (un hilo). |
| Autoescalado de nodos | Cluster Autoscaler sobre el grupo `app` (2–6 nodos) | Hasta 8 réplicas × 2 pods + pasarela necesitan ≈ 10 vCPU solicitadas. |
| `bd-bloqueo`, Redis y Postgres | Grupo `sistema`, fijo | Estables mientras `app` crece y decrece. Los datos van en el clúster (el plan dejaba "gestionado o en el clúster" por confirmar). |
| Generador de carga | JMeter en un nodo propio (`carga`) con taint | El plan pide generador aparte para que no sea el límite. Es un nodo y no una EC2 suelta, para operarlo con el mismo kubectl. |
| Acceso | `port-forward` con los mismos puertos de local | Ningún puerto abierto a Internet; tus enlaces no cambian: Grafana `localhost:30300`, panel `localhost:8088`. |
| Balanceo | `Service` ClusterIP de Kubernetes (kube-proxy) | El generador corre dentro del clúster. Un balanceador NLB no aporta a lo que se mide. |

Cuotas de la cuenta (consultadas en modo lectura): 64 vCPU On-Demand estándar y 256 Spot. El diseño usa como máximo 4+24+4 = 32 vCPU. Hoy no hay clústeres EKS.

## 3. Costo estimado (on-demand, precios de lista aproximados de us-east-1; verificar antes de crear)

| Recurso | Costo/h |
|---|---|
| Plano de control EKS | 0,10 |
| 2 × m7g.large (sistema) | 0,16 |
| 2–6 × m7g.xlarge (app) | 0,33 – 0,98 |
| 1 × c7g.xlarge (carga) | 0,15 |
| Discos EBS, ECR, tráfico | < 0,02 |
| **Total** | **≈ 0,75 en reposo · ≈ 1,40 en el pico** |

Una sesión completa de unas 4–5 h (crear, humo, 2 ejecuciones, margen) cuesta del orden de **USD 4–8**. Si se deja encendido por olvido, ≈ USD 18–34 al día.
Control: `99-destruir.sh` borra todo y verifica; se recomienda además una alarma de presupuesto.

## 4. Qué se construyó (todo en `experimentos/exp2/aws/`)

| Archivo | Para qué |
|---|---|
| `eksctl-cluster.yaml` | Clúster, 3 grupos de nodos, complementos (metrics-server, EBS CSI) |
| `helm-values-monitoreo.yaml` | Prometheus + Grafana + kube-state-metrics |
| `k8s/generar.py` → `00-datos`, `10-plataforma` (con HPA), `20-podmonitor`, `30-carga` | Manifiestos |
| `dashboards/gen-dashboard-exp2.py` | Tablero `exp2asr` (18 paneles): E-1 (p95 vs 250 ms, solicitudes/s vs 133, rechazos), equilibrio (réplicas, CPU vs 60 %, nodos), hilo único, y los paneles de D-3 de EXP-1 |
| `imagenes/Dockerfile.jmeter`, `Dockerfile.panel` | Imágenes de carga y del panel |
| `scripts/01..04, reiniciar-estado, 10-run-exp2, 99-destruir` | Crear, publicar, desplegar, acceder, ejecutar, destruir |
| `scripts/recolectar_exp2.py` | p95 del pico (completo y tras el equilibrio), réplicas y momento de equilibrio, hilo único, rechazos; escribe `metricas.md/json` |
| `exp1/carga/init.groovy` | Nuevo perfil `rampa` (400 → 8.000/min); el perfil constante de EXP-1 no cambia |
| `exp1/control/` (panel) | Botón **"Rampa al pico"**: 1 min a 400/min, rampa de 2 min, pico 1–15 min, con conflictos al azar; el semáforo usa 250 ms en ese modo |

## 5. Carga del experimento
- **JMeter (ejecuciones oficiales):** 60 s a 400/min, rampa lineal de 120 s hasta 8.000/min y pico de 900 s; 2 ejecuciones con semillas 1 y 2.
- **Conflictos:** 1 de cada 20 llegadas dispara 5–10 solicitudes simultáneas (mismos tipos que EXP-1). **Decisión de diseño:** las solicitudes de los conflictos cuentan *dentro* de las 8.000/min, para que el total de reservas por minuto sea el del ASR (por eso las llegadas normales son ≈ 5.800/min).
- **Asientos:** ≈ 94.000 llegadas normales y ≈ 28.000 asientos de conflictos caben en los 130.000 del evento (con poco margen).
- **Panel de inyección:** pensado para explorar y demostrar en vivo. No sustituye a JMeter en las ejecuciones oficiales.

## 6. Fases y puntos de aprobación
1. **Ok al diseño** (este documento).
2. Crear clúster + monitoreo (~20 min). Verificar nodos, metrics-server, Grafana y la fuente de datos `prom`.
3. Publicar imágenes y desplegar. Verificar `taq` y el tablero `exp2asr`.
4. **Prueba de humo** (≈ 10 min, `PICO_S=60 CAL_S=20 RAMPA_S=30`): confirma que las métricas, el HPA y el recolector funcionan.
5. **Ok para las 2 ejecuciones oficiales** (≈ 25 min cada una + reinicio).
6. Resultados en `exp2/resultados/corrida-N/` (Markdown + JSON, como EXP-1) y tablero guardado como evidencia.
7. Destruir todo y verificar. (Si se va a hacer EXP-3 enseguida, se puede mantener el clúster.)

## 7. Riesgos y límites que hay que anotar en los resultados
- **Nada de esto está probado en AWS.** Lo local no puede correr 8 réplicas; el humo es la primera prueba real. Es probable que haya ajustes (nombres de servicios de Prometheus, uid del datasource, permisos).
- **El arranque de nodos tarda** (≈ 2–4 min): durante la rampa pueden verse pods pendientes y un p95 mayor. Es parte de lo que mide el experimento, y por eso se reportan el p95 con arranque y el p95 tras el equilibrio.
- **Redis como broker y como caché es una sola instancia.** Si es el cuello de botella, el tablero lo mostrará en las colas y no en el hilo único; se anotaría como hallazgo.
- **p95 interpolado:** el límite de 250 ms no es borde de cubeta del histograma. Se reporta el p95 y el % bajo 200 ms y 300 ms.
- **Una sola zona y una sola máquina por rol:** no se prueba tolerancia a fallas de zona.
- **Resultados distintos a EXP-1:** EXP-1 se corrió en kind con una réplica. No se comparan latencias entre ambos entornos.

## 8. Lo que necesito de ti para desplegar
1. **Ok al diseño** y a la región `us-east-1`.
2. **Cómo ejecuto contra AWS:** (a) con tus credenciales locales de AWS CLI y los scripts (necesita `eksctl`, que no está instalado: `brew install eksctl`), o (b) lo corres tú con los scripts y yo superviso y analizo. La conexión de AWS que tengo en esta sesión es de solo lectura útil para consultas, y hoy pide volver a iniciar sesión.
3. **Presupuesto:** ¿tope de gasto para la sesión y alarma de presupuesto?
4. **EXP-3:** ¿se reutiliza el mismo clúster, o se destruye al terminar EXP-2?

## 9. EXP-1 también en AWS (agregado 2026-11-22)

El mismo clúster sirve para EXP-1: es la misma plataforma con **una sola réplica por pod**, a 400/min, 60 s + 720 s.

| Pieza | Cómo queda |
|---|---|
| Modo del clúster | `scripts/modo.sh exp1` fija el autoescalador en 1–1 réplica; `modo.sh exp2` lo deja en 1–8. También se cambia desde el panel web. |
| Tablero | El `exp1asr` (L-1 y D-3) se carga en el mismo Grafana junto al `exp2asr` (`dashboards/exp1-dashboard.yaml`). |
| Ejecución oficial | `scripts/11-run-exp1.sh <n> <semilla>`: JMeter en el nodo `carga`, mismo verificador y mismas gráficas; resultados en `exp1/resultados-aws/corrida-N` (no pisa los locales). |
| Uso a demanda | El panel web (puerto 8088, ya dentro del clúster) tiene tráfico normal, inyección de conflictos y rampa al pico, con el mismo semáforo y las mismas tarjetas. |
| Reiniciar estado | Funciona desde el panel: la imagen incluye `kubectl` y un `ServiceAccount` con permisos solo sobre el namespace `taq`. |
| Límite de pods | Tarjeta "Límite de pods" del panel: máximo de réplicas de 1 a 8 (y botón "1 fija (EXP-1)"); aplica a `nodo-entrada`, `nodo-reserva` y `nodo-pasarela`, también con la prueba en curso. Muestra réplicas actuales / máximo. |

**Para qué sirve repetir EXP-1 en AWS:** corre en un entorno sin la carga de otras aplicaciones (en local el load average estuvo entre 9 y 13) y con el generador en su propia máquina. Los resultados locales se conservan; los de AWS se reportan aparte como confirmación en entorno limpio. Costo adicional: unos 25 min por corrida, ≈ USD 0,5–0,6 cada una.
