#!/usr/bin/env bash
# Una corrida de EXP-1 en EKS (1 réplica por pod, 400/min, 12 min), con JMeter dentro del clúster.
# Uso: 11-run-exp1.sh <n> <semilla>      Los resultados van a experimentos/exp1/resultados-aws/corrida-N
set -euo pipefail
N=${1:?numero}; SEMILLA=${2:?semilla}
AQUI="$(cd "$(dirname "$0")" && pwd)"; AWS_DIR="$(dirname "$AQUI")"; EXPS="$(cd "$AWS_DIR/../.." && pwd)"
SALIDA="$EXPS/exp1/resultados-aws/corrida-$N"; mkdir -p "$SALIDA"
export JAVA_HOME=${JAVA_HOME:-/opt/homebrew/opt/openjdk@21}
"$AQUI/modo.sh" exp1 >/dev/null
echo "[1/6] Reiniciando estado"; "$AQUI/reiniciar-estado.sh"; "$AQUI/04-acceso.sh" >/dev/null
until curl -sf localhost:30090/actuator/health >/dev/null && curl -sf localhost:30080/actuator/health >/dev/null; do sleep 2; done
CARGA_ANTES=$(kubectl -n taq top node 2>/dev/null | awk 'NR>1 {s+=$3} END {print s/(NR-1)"% CPU medio de nodos"}')
echo "[2/6] Carga con JMeter en el nodo 'carga' (semilla $SEMILLA, 60 s + 720 s a 400/min)"
kubectl -n taq exec deploy/jmeter -- sh -c "rm -rf /resultados/*; jmeter -n -t /carga/plan-exp1.jmx -Jdir=/carga -Jsemilla=$SEMILLA \
  -Jcalentamiento_s=60 -Jtrafico_s=720 -Jhost=nodo-entrada:8080 -Jttl_s=480 -Jbitacora=/resultados/bitacora.csv \
  -Jejecucion_json=/resultados/ejecucion.json -l /resultados/jmeter.jtl -j /resultados/jmeter.log" 2>&1 | grep -E "summary =|Starting|end of run" | tail -3 || true
sleep 15
POD=$(kubectl -n taq get pod -l app=jmeter -o jsonpath='{.items[0].metadata.name}')
kubectl -n taq cp "$POD:/resultados" "$SALIDA" -c jmeter
echo "$CARGA_ANTES → $(kubectl -n taq top node 2>/dev/null | awk 'NR>1 {s+=$3} END {print s/(NR-1)"% CPU medio de nodos"}')" > "$SALIDA/carga-maquina.txt"
echo "[3/6] Métricas"; "$EXPS/.venv/bin/python" "$EXPS/exp1/scripts/recolectar.py" "$SALIDA" >/dev/null
echo "[4/6] Verificación D-3"; set +e
"$JAVA_HOME/bin/java" -Dloader.main=co.uniandes.taq.verificador.Verificador -cp "$EXPS/plataforma/target/taq.jar" \
  org.springframework.boot.loader.launch.PropertiesLauncher "$SALIDA/bitacora.csv" "$SALIDA" http://localhost:30090 jdbc:postgresql://localhost:30432/taq 480 >/dev/null
VER=$?; set -e
curl -sf -u "admin:$(cat "$AWS_DIR/.grafana-pass")" localhost:30300/api/dashboards/uid/exp1asr > "$SALIDA/tablero-grafana.json" || true
echo "[5/6] Resumen"; "$EXPS/.venv/bin/python" "$EXPS/exp1/scripts/resumen_corrida.py" "$SALIDA" "$N"
echo "Listo: $SALIDA (verificación D-3, código: $VER)"
