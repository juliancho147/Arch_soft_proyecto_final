#!/usr/bin/env bash
# Cambia el clúster entre los dos experimentos fijando el rango del autoescalador:
#   modo.sh exp1  -> 1 réplica fija por pod (EXP-1: una sola réplica, 400/min)
#   modo.sh exp2  -> 1 a 8 réplicas, objetivo CPU 60 % (EXP-2)
set -euo pipefail
case "${1:-}" in
  exp1) MIN=1; MAX=1 ;;
  exp2) MIN=1; MAX=${MAX_REPLICAS:-8} ;;
  *) echo "uso: modo.sh exp1|exp2"; exit 1 ;;
esac
for h in nodo-entrada nodo-reserva nodo-pasarela; do
  kubectl -n taq patch hpa $h --type merge -p "{\"spec\":{\"minReplicas\":$MIN,\"maxReplicas\":$MAX}}" >/dev/null
  [ "$1" = exp1 ] && kubectl -n taq scale deploy/$h --replicas=1 >/dev/null
done
echo "Modo $1: autoescalado ${MIN}–${MAX} réplicas por pod."; kubectl -n taq get hpa
