# EXP-1 — Reserva de asientos en operación normal (L-1 y D-3)

Hipótesis, tácticas y criterios: ver [`../../Plan-Experimentos-TAQ.md`](../../Plan-Experimentos-TAQ.md#exp-1--reserva-de-asientos-en-operación-normal-l-1-y-d-3--aprobado).
**Resultados:** [`resultados/resumen-exp1.md`](resultados/resumen-exp1.md).

## Cómo se ejecuta

```bash
# 1. Compilar e imagen (desde experimentos/plataforma)
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
mvn -q -DskipTests package && docker build -t taq/plataforma:1.0 .

# 2. Clúster y despliegue (desde experimentos/exp1)
kind create cluster --name taq --config k8s/kind-config.yaml
kind load docker-image taq/plataforma:1.0 --name taq
kubectl apply -f k8s/00-datos.yaml -f k8s/10-plataforma.yaml -f k8s/20-observabilidad.yaml -f k8s/30-grafana-dashboard.json

# 3. Corridas (cada una ≈ 14 min) y consolidado
scripts/run-todas.sh                       # o: scripts/run.sh <n> <semilla>
../.venv/bin/python scripts/resumen_exp1.py
scripts/entorno.sh
```

Puertos locales: gateway `:30080`, `bd_bloqueo` `:30090`, PostgreSQL `:30432`, Prometheus `:30900`, **Grafana `:30300`** (tablero «EXP-1 Reserva en operación normal», sin contraseña).

## Qué hace una corrida

1. Reinicia el estado: `bd_bloqueo` (en memoria), `reserva_log` y las colas.
2. JMeter ejecuta 60 s de calentamiento + 720 s de tráfico: llegadas de Poisson a 400/min; 70 % confirma el pago (5–40 s después) y 30 % abandona. Una de cada 20 llegadas dispara un conflicto de 5 a 10 solicitudes simultáneas: mismo asiento, grupos de 2–4 asientos que se cruzan, o asiento ya vendido. Los abandonados se vuelven a pedir a los 4 min (se espera rechazo) y pasados los 8 min (se espera éxito).
3. Recolecta de Prometheus (ventana de 720 s, sin calentamiento) y de la bitácora del cliente.
4. El verificador cruza la bitácora con la auditoría y el estado de `bd_bloqueo` (consultados por su cola de operaciones) y con `reserva_log` en PostgreSQL.

La semilla fija el calendario de llegadas, asientos y conflictos. Los eventos que dependen de una respuesta (confirmaciones, revisiones, qué asiento vendido se ataca) dependen además de los tiempos reales.

## Mapa del plan al código

| Elemento de arquitectura | Implementación |
|---|---|
| `componente_api_gateway`, `cola_solicitud`, `cola_respuesta` | `gateway/GatewayController` (pod `nodo-entrada`); colas como listas de Redis; cola acotada a 5.000 |
| receptor, gestor, consultor, confirmador | `reserva/NodoReserva` (pod `nodo-reserva`, 16 consumidores) |
| `proceso_bd_bloqueo` (`cola_operacion`, `hilo_unico`, `estado_asiento`, `proceso_vencimiento`) | `bloqueo/BdBloqueo` (pod `bd-bloqueo`): un `ThreadPoolExecutor` de 1 hilo sobre una cola; el vencimiento barre cada 1 s |
| `cache_asiento` | Redis (se precargan 4 de cada 5 asientos; el resto es *miss* y consulta `bd_reserva`) |
| `bd_reserva` | PostgreSQL 16: `asiento` (130.000 filas) y `reserva_log` **sin restricción de unicidad**, para que una doble reserva se vea y no la oculte la base |
| Persistencia asíncrona | `cola_persistencia` (Redis) → hilo persistidor |
| Pasarela de pago simulada | `pasarela/PasarelaSim`, latencia fija de 150 ms, sin fallas |

## Desviaciones respecto al plan (para que quede claro qué se cambió)

- **kind en lugar de minikube**: minikube no estaba instalado y kind ya lo estaba. Es Kubernetes local con los mismos manifiestos.
- **JDK 21 para compilar, Java 17 para ejecutar** (`--release 17`, JRE Temurin 17 en los pods).
- **Broker de colas: Redis** (el plan lo dejaba por confirmar). Redis también hace de `cache_asiento`.
- **CPU y memoria** se miden con las métricas de la JVM (`process_cpu_usage`, heap), no con cAdvisor; son porcentaje del proceso, no de la máquina.
- **Tableros de Grafana**: el tablero queda provisionado y se guarda su definición; las imágenes de evidencia se generan con matplotlib a partir de las mismas series de Prometheus (Grafana no trae el renderizador de imágenes).
- **Cliente JMeter**: las llamadas HTTP se hacen desde un sampler JSR223 (Groovy) y no desde el HTTP Request nativo, para controlar llegadas, conflictos simultáneos y bitácora.
- Todo (clúster, JMeter, Prometheus, Grafana) corre en una sola máquina; ver [`resultados/entorno.md`](resultados/entorno.md).
- Esta primera versión no ejecuta en AWS EKS.

## Panel de control (uso interactivo)

Para probar a mano, sin JMeter: `python3 control/servidor.py` y abrir http://localhost:8088.
Permite iniciar tráfico normal a 400 solicitudes/min (el ASR) durante 1 a 20 minutos e inyectar
compras simultáneas a demanda (misma silla, grupos que se cruzan, silla ya vendida), con semáforos de L-1 y D-3.
Guarda un resumen en `resultados/panel/sesion-*/`. No sustituye a las 3 corridas oficiales con semilla.
