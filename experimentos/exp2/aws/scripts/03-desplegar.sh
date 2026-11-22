#!/usr/bin/env bash
# Despliega datos, plataforma (con autoescalado), PodMonitor, generador de carga y tablero de EXP-2.
set -euo pipefail
source "$(dirname "$0")/00-config.sh"
( cd "$AQUI_AWS/k8s" && ECR=$ECR python3 generar.py >/dev/null )
( cd "$AQUI_AWS/dashboards" && python3 gen-dashboard-exp2.py >/dev/null )
kubectl apply -f "$AQUI_AWS/k8s/00-datos.yaml"
kubectl -n taq rollout status deploy/postgres deploy/redis --timeout=300s
kubectl apply -f "$AQUI_AWS/k8s/10-plataforma.yaml" -f "$AQUI_AWS/k8s/20-podmonitor.yaml" -f "$AQUI_AWS/k8s/30-carga.yaml" \
              -f "$AQUI_AWS/dashboards/exp2-dashboard.yaml" -f "$AQUI_AWS/dashboards/exp1-dashboard.yaml"
for d in bd-bloqueo nodo-reserva nodo-entrada nodo-pasarela jmeter panel; do kubectl -n taq rollout status deploy/$d --timeout=300s; done
kubectl -n taq get pods,hpa
