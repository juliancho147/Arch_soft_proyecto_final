#!/usr/bin/env bash
# Apaga TODO lo que cobra: túneles, clúster (nodos, volúmenes, balanceadores) y, con --ecr, los repositorios de imágenes.
set -uo pipefail
source "$(dirname "$0")/00-config.sh"
pkill -f "port-forward" 2>/dev/null
kubectl delete namespace taq monitoring --wait=true --timeout=300s 2>/dev/null     # libera discos y balanceadores creados por el clúster
eksctl delete cluster -f "$AQUI_AWS/eksctl-cluster.yaml" --disable-nodegroup-eviction --wait
if [ "${1:-}" = "--ecr" ]; then
  "$EXPS/.venv/bin/python" "$AQUI_AWS/scripts/ecr.py" borrar
fi
echo "Verifica con: eksctl get cluster --region $AWS_REGION  (debe salir vacío)"