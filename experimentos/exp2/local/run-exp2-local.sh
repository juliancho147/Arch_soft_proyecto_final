#!/usr/bin/env bash
# Una ejecución completa de EXP-2 en LOCAL (kind, tope de 5 réplicas). Uso: run-exp2-local.sh <n> <semilla>
# Ensayo rápido: PICO_S=60 CAL_S=20 RAMPA_S=30 TASA_PICO=2000 run-exp2-local.sh 0 1
set -euo pipefail
N=${1:?numero}; SEMILLA=${2:?semilla}
CAL=${CAL_S:-60}; RAMPA=${RAMPA_S:-120}; PICO=${PICO_S:-900}; TASA_PICO=${TASA_PICO:-8000}; HILOS=${HILOS:-600}
AQUI="$(cd "$(dirname "$0")" && pwd)"; EXP2="$(dirname "$AQUI")"; EXPS="$(dirname "$EXP2")"
SALIDA=${SALIDA:-"$EXP2/resultados/corrida-$N"}; mkdir -p "$SALIDA"
TMP="/private/tmp/claude-501/exp2-crudo-$N"; rm -rf "$TMP"; mkdir -p "$TMP"
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
echo "[1/6] Reiniciando estado y volviendo a 1 réplica"
kubectl -n taq scale deploy/nodo-entrada deploy/nodo-reserva deploy/nodo-pasarela --replicas=1 >/dev/null
kubectl -n taq exec deploy/postgres -- psql -U taq -d taq -qc "TRUNCATE reserva_log RESTART IDENTITY" >/dev/null
kubectl -n taq exec deploy/redis -- sh -c 'redis-cli --scan --pattern "cola_*" | xargs -r redis-cli del >/dev/null; true'
kubectl -n taq rollout restart deploy/bd-bloqueo deploy/nodo-entrada deploy/nodo-reserva deploy/nodo-pasarela >/dev/null
for d in bd-bloqueo nodo-entrada nodo-reserva nodo-pasarela; do kubectl -n taq rollout status deploy/$d --timeout=240s >/dev/null; done
until curl -sf localhost:30090/actuator/health >/dev/null && curl -sf localhost:30080/actuator/health >/dev/null; do sleep 1; done
sleep 25   # Prometheus ve los pods nuevos y el HPA se asienta en 1 réplica
CARGA_ANTES=$(sysctl -n vm.loadavg | awk '{print $2}')
# Vigilante de memoria: si el nodo de kind pasa de 7,4 GiB se aborta la carga (evita que Docker mate pods y falsee el resultado)
( while true; do m=$(docker stats --no-stream --format '{{.MemUsage}}' taq-control-plane | awk -F/ '{print $1}'); echo "$(date +%s) $m" >> "$TMP/memoria.log"
  v=$(echo "$m" | sed 's/GiB//;s/MiB//;s/ //g'); case "$m" in *GiB*) awk -v v="$v" 'BEGIN{exit !(v>7.4)}' && { echo ABORTADO > "$TMP/aborto.txt"; pkill -f ApacheJMeter; };; esac; sleep 10; done ) &
VIGILANTE=$!
echo "[2/6] Carga con JMeter (semilla $SEMILLA: ${CAL}s calentamiento + ${RAMPA}s rampa + ${PICO}s pico a $TASA_PICO/min, tope 5 réplicas)"
JVM_ARGS="-Xms1g -Xmx2g" jmeter -n -t "$EXPS/exp1/carga/plan-exp1.jmx" -Jdir="$EXPS/exp1/carga" -Jsemilla="$SEMILLA" \
  -Jcalentamiento_s="$CAL" -Jtrafico_s=$((RAMPA+PICO)) -Jperfil=rampa -Jrampa_s="$RAMPA" -Jtasa_pico="$TASA_PICO" -Jdescuenta_conflictos=true \
  -Jhilos="$HILOS" -Jttl_s=480 -Jbitacora="$TMP/bitacora.csv" -Jejecucion_json="$TMP/ejecucion.json" \
  -l "$TMP/jmeter.jtl" -j "$TMP/jmeter.log" 2>&1 | grep -E "summary =|Starting|end of run" | tail -4 || true
kill $VIGILANTE 2>/dev/null || true
echo "[3/6] Esperando a que la persistencia asíncrona vacíe su cola"
for i in $(seq 1 60); do d=$(curl -s localhost:30900/api/v1/query --data-urlencode 'query=sum(taq_cola_persistencia_profundidad)' | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(int(float(r[0]['value'][1])) if r else 0)"); [ "$d" = "0" ] && break; sleep 5; done
sleep 10
echo "$CARGA_ANTES → $(sysctl -n vm.loadavg | awk '{print $2}')" > "$SALIDA/carga-maquina.txt"
cp "$TMP"/* "$SALIDA"/
echo "[4/6] Métricas de Prometheus"
python3 "$EXP2/aws/scripts/recolectar_exp2.py" "$SALIDA" "$PICO" "$CAL" "$RAMPA" http://localhost:30900
echo "[5/6] Verificación D-3"
set +e
"$JAVA_HOME/bin/java" -Dloader.main=co.uniandes.taq.verificador.Verificador -cp "$EXPS/plataforma/target/taq.jar" \
  org.springframework.boot.loader.launch.PropertiesLauncher "$SALIDA/bitacora.csv" "$SALIDA" http://localhost:30090 jdbc:postgresql://localhost:30432/taq 480 >/dev/null
VER=$?; set -e
curl -sf localhost:30300/api/dashboards/uid/exp2asr > "$SALIDA/tablero-grafana.json" || true
echo "[6/6] Resumen"
python3 "$EXP2/aws/scripts/resumen_exp2.py" "$SALIDA" "$N" "local, tope 5 réplicas"
echo "Listo: $SALIDA (verificación D-3, código: $VER)"
