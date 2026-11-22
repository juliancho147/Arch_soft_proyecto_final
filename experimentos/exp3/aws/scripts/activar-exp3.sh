#!/usr/bin/env bash
# Prepara EXP-3 en el clúster: genera los manifiestos, aplica el tablero y los pods nuevos, y enciende TAQ_DETECCION=on en
# nodo-entrada y bd-bloqueo (imagen 1.1). Para volver a EXP-1/EXP-2:  activar-exp3.sh volver
set -euo pipefail
source "$(dirname "$0")/../../../exp2/aws/scripts/00-config.sh"
EXP3="$(cd "$(dirname "$0")/.." && pwd)"
if [ "${1:-}" = "volver" ]; then
  kubectl delete -f "$EXP3/k8s/20-deteccion-respuesta.yaml" --ignore-not-found
  kubectl apply -f "$EXPS/exp2/aws/k8s/10-plataforma.yaml"       # imagen 1.0, sin TAQ_DETECCION
  for d in bd-bloqueo nodo-entrada; do kubectl -n taq rollout status deploy/$d --timeout=300s; done
  exit 0
fi
( cd "$EXP3/k8s" && ECR=$ECR python3 generar_exp3.py >/dev/null )
( cd "$EXP3/dashboards" && python3 gen-dashboard-exp3.py >/dev/null )
kubectl apply -f "$EXP3/dashboards/exp3-dashboard.yaml"
kubectl apply -f "$EXP3/k8s/10-plataforma-exp3.yaml" -f "$EXP3/k8s/20-deteccion-respuesta.yaml"
for d in bd-bloqueo nodo-entrada deteccion respuesta; do kubectl -n taq rollout status deploy/$d --timeout=300s; done
kubectl -n taq get pods -o wide | grep -E "deteccion|respuesta|nodo-entrada|bd-bloqueo"
