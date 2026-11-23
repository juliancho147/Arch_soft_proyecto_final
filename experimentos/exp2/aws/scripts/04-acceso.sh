#!/usr/bin/env bash
# Abre túneles (port-forward) con los MISMOS puertos que usamos en local; si un túnel se cae, se reabre solo. Nada queda expuesto a Internet.
#   Grafana http://localhost:30300/d/exp2asr   Panel http://localhost:8088   Prometheus :30900   gateway :30080   bd_bloqueo :30090   Postgres :30432
source "$(dirname "$0")/00-config.sh" 2>/dev/null
pkill -f "tunel-taq" 2>/dev/null; pkill -f "port-forward" 2>/dev/null; sleep 1
tunel() {  # tunel <namespace> <svc> <puerto-local:puerto-svc>
  ( exec -a "tunel-taq-$3" bash -c "while true; do kubectl -n $1 port-forward svc/$2 $3 >/dev/null 2>&1; sleep 2; done" ) &
}
tunel monitoring kube-prometheus-stack-grafana 30300:80
tunel monitoring kube-prometheus-stack-prometheus 30900:9090
tunel taq panel 8088:8088
tunel taq nodo-entrada 30080:8080
tunel taq bd-bloqueo 30090:8080
tunel taq postgres 30432:5432
sleep 4; echo "Túneles abiertos (taq-exp). Contraseña de Grafana: $(cat "$AQUI_AWS/.grafana-pass" 2>/dev/null)"
