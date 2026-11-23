# Entorno de ejecución de EXP-1

| Dato | Valor |
|---|---|
| Fecha del registro | 2026-11-18 12:00 -05 |
| Máquina | Apple M5, 10 núcleos, 16 GB de RAM |
| Sistema operativo | macOS 27.0.1 |
| Docker (CPUs / memoria asignadas) | 10 CPUs / 7.8 GiB |
| Kubernetes local | kind v0.33.0 con 1 nodo (`kind-taq`), kubectl v1.34.1 |
| JMeter | 5.6.3 (en la máquina anfitriona, fuera del clúster) |
| JDK de compilación / JRE de ejecución | 21.0.12.1 (--release 17) / Temurin 17 en los pods |
| Commit del código | 068c19e (rama actualizar-hipotesis-experimentos) |

## Pods y límites de recursos

| Pod | Réplicas | CPU (solicitud / límite) | Memoria (solicitud / límite) |
|---|---|---|---|
| bd-bloqueo | 1 | 250m / 1 | 256Mi / 384Mi |
| grafana | 1 | 100m / 1 | 128Mi / 384Mi |
| nodo-entrada | 1 | 250m / 2 | 256Mi / 512Mi |
| nodo-pasarela | 1 | 250m / 1 | 256Mi / 384Mi |
| nodo-reserva | 1 | 250m / 2 | 256Mi / 512Mi |
| postgres | 1 | 250m / 1 | 256Mi / 512Mi |
| prometheus | 1 | 100m / 1 | 256Mi / 768Mi |
| redis | 1 | 100m / 1 | 128Mi / 384Mi |

Todo comparte la misma máquina: clúster, JMeter, Prometheus y Grafana. Las cifras de latencia incluyen esa competencia por recursos.
