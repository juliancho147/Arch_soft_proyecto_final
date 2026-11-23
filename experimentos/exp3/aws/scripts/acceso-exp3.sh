#!/usr/bin/env bash
# Agrega los túneles de EXP-3 SIN cerrar los de 04-acceso.sh:  detección :30091 y respuesta :30092 (el resto ya existe:
# gateway :30080, bd_bloqueo :30090, Prometheus :30900, Grafana :30300).
tunel() {  # tunel <namespace> <svc> <puerto-local:puerto-svc>
  pgrep -f "tunel-taq-$3" >/dev/null && return
  ( exec -a "tunel-taq-$3" bash -c "while true; do kubectl -n $1 port-forward svc/$2 $3 >/dev/null 2>&1; sleep 2; done" ) &
}
tunel taq deteccion 30091:8080
tunel taq respuesta 30092:8080
sleep 3; echo "Túneles de EXP-3 abiertos: detección :30091, respuesta :30092"
