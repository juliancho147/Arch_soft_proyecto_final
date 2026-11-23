#!/usr/bin/env bash
# Ejecuta UNA corrida completa de EXP-1: reinicia el estado, lanza JMeter, recolecta métricas y verifica D-3.
# Uso: run.sh <n> <semilla> [calentamiento_s=60] [trafico_s=720] [carpeta_resultados]
set -euo pipefail
N=${1:?numero de corrida}; SEMILLA=${2:?semilla}; CAL=${3:-60}; TRAF=${4:-720}
AQUI="$(cd "$(dirname "$0")" && pwd)"; EXP="$(dirname "$AQUI")"; RAIZ="$(dirname "$EXP")"
SALIDA=${5:-"$EXP/resultados/corrida-$N"}
TTL=${TTL_S:-480}   # solo se cambia para pruebas rápidas del script; las corridas reales usan 480
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
mkdir -p "$SALIDA"
# Los datos crudos se escriben fuera de OneDrive (para que su sincronización no compita por CPU y disco) y se copian al terminar.
TMP="/private/tmp/claude-501/exp1-crudo-$N"; rm -rf "$TMP"; mkdir -p "$TMP"

echo "[1/6] Reiniciando estado (bd_bloqueo en memoria, reserva_log, colas)"
kubectl -n taq exec deploy/postgres -- psql -U taq -d taq -qc "TRUNCATE reserva_log RESTART IDENTITY" >/dev/null
kubectl -n taq exec deploy/redis -- sh -c 'redis-cli --scan --pattern "cola_*" | xargs -r redis-cli del >/dev/null; true'
kubectl -n taq rollout restart deploy/bd-bloqueo >/dev/null
kubectl -n taq rollout status deploy/bd-bloqueo --timeout=120s >/dev/null
until curl -sf localhost:30090/actuator/health >/dev/null; do sleep 1; done
sleep 8   # que Prometheus vuelva a ver el pod nuevo
CARGA_ANTES=$(sysctl -n vm.loadavg | awk '{print $2}')

echo "[2/6] Carga con JMeter (semilla $SEMILLA, ${CAL}s calentamiento + ${TRAF}s tráfico)"
jmeter -n -t "$EXP/carga/plan-exp1.jmx" -Jdir="$EXP/carga" -Jsemilla="$SEMILLA" \
  -Jcalentamiento_s="$CAL" -Jtrafico_s="$TRAF" -Jttl_s="$TTL" \
  -Jbitacora="$TMP/bitacora.csv" -Jejecucion_json="$TMP/ejecucion.json" \
  -l "$TMP/jmeter.jtl" -j "$TMP/jmeter.log" 2>&1 | grep -E "summary =|Starting|end of run" || true
sleep 12   # última raspada de Prometheus
echo "$CARGA_ANTES → $(sysctl -n vm.loadavg | awk '{print $2}')" > "$SALIDA/carga-maquina.txt"
cp "$TMP"/* "$SALIDA"/

echo "[3/6] Métricas desde Prometheus"
"$RAIZ/.venv/bin/python" "$AQUI/recolectar.py" "$SALIDA" >/dev/null

echo "[4/6] Verificación D-3"
set +e
"$JAVA_HOME/bin/java" -Dloader.main=co.uniandes.taq.verificador.Verificador -cp "$RAIZ/plataforma/target/taq.jar" \
  org.springframework.boot.loader.launch.PropertiesLauncher "$SALIDA/bitacora.csv" "$SALIDA" \
  http://localhost:30090 jdbc:postgresql://localhost:30432/taq "$TTL" >/dev/null
VER=$?
set -e

echo "[5/6] Evidencia de Grafana"
curl -sf localhost:30300/api/dashboards/uid/exp1asr > "$SALIDA/tablero-grafana.json" || true

echo "[6/6] Resumen de la corrida"
"$RAIZ/.venv/bin/python" "$AQUI/resumen_corrida.py" "$SALIDA" "$N"
echo "Listo: $SALIDA (verificación D-3 código de salida: $VER)"
