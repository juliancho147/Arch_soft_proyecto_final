#!/usr/bin/env bash
# Una ejecución completa de EXP-2 en EKS: reinicia estado, rampa al pico con JMeter (dentro del clúster), recolecta y verifica.
# Uso: 10-run-exp2.sh <n> <semilla> [pico_s=900]      (humo: PICO_S=60 CAL_S=20 RAMPA_S=30 10-run-exp2.sh 0 1)
set -euo pipefail
N=${1:?numero}; SEMILLA=${2:?semilla}
CAL=${CAL_S:-60}; RAMPA=${RAMPA_S:-120}; PICO=${PICO_S:-900}; TASA_PICO=${TASA_PICO:-8000}; HILOS=${HILOS:-600}
AQUI="$(cd "$(dirname "$0")" && pwd)"; AWS_DIR="$(dirname "$AQUI")"; EXPS="$(cd "$AWS_DIR/../.." && pwd)"
SALIDA="$EXPS/exp2/resultados/corrida-$N"; mkdir -p "$SALIDA"
export JAVA_HOME=${JAVA_HOME:-/opt/homebrew/opt/openjdk@21}
echo "[1/6] Reiniciando estado y volviendo a 1 réplica"; "$AQUI/reiniciar-estado.sh"
"$AQUI/04-acceso.sh" >/dev/null; until curl -sf localhost:30090/actuator/health >/dev/null; do sleep 2; done
kubectl -n taq top nodes 2>/dev/null | head -5 || true
echo "[2/6] Carga con JMeter en el nodo 'carga' (semilla $SEMILLA: ${CAL}s calentamiento + ${RAMPA}s rampa + ${PICO}s pico a $TASA_PICO/min)"
kubectl -n taq exec deploy/jmeter -- sh -c "rm -rf /resultados/*; jmeter -n -t /carga/plan-exp1.jmx -Jdir=/carga -Jsemilla=$SEMILLA \
  -Jcalentamiento_s=$CAL -Jtrafico_s=$((RAMPA+PICO)) -Jperfil=rampa -Jrampa_s=$RAMPA -Jtasa_pico=$TASA_PICO -Jdescuenta_conflictos=true \
  -Jhilos=$HILOS -Jhost=nodo-entrada:8080 -Jttl_s=480 -Jbitacora=/resultados/bitacora.csv -Jejecucion_json=/resultados/ejecucion.json \
  -l /resultados/jmeter.jtl -j /resultados/jmeter.log" 2>&1 | grep -E "summary =|Starting|end of run" || true
sleep 15
echo "[3/6] Copiando resultados del generador"
POD=$(kubectl -n taq get pod -l app=jmeter -o jsonpath='{.items[0].metadata.name}')
kubectl -n taq cp "$POD:/resultados" "$SALIDA" -c jmeter
echo "[4/6] Métricas de Prometheus (réplicas, p95, hilo único, rechazos)"
python3 "$AQUI/recolectar_exp2.py" "$SALIDA" "$PICO" "$CAL" "$RAMPA"
echo "[5/6] Verificación D-3 (mismo verificador de EXP-1)"
set +e
"$JAVA_HOME/bin/java" -Dloader.main=co.uniandes.taq.verificador.Verificador -cp "$EXPS/plataforma/target/taq.jar" \
  org.springframework.boot.loader.launch.PropertiesLauncher "$SALIDA/bitacora.csv" "$SALIDA" http://localhost:30090 jdbc:postgresql://localhost:30432/taq 480 >/dev/null
VER=$?; set -e
echo "[6/6] Evidencia de Grafana"
curl -sf -u "admin:$(cat "$AWS_DIR/.grafana-pass")" localhost:30300/api/dashboards/uid/exp2asr > "$SALIDA/tablero-grafana.json" || true
echo "Listo: $SALIDA (verificación D-3, código de salida: $VER)"
