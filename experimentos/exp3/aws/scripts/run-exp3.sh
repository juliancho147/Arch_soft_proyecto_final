#!/usr/bin/env bash
# Una ejecución completa de EXP-3 en EKS: reinicia estado, corre JMeter dentro del clúster con tráfico legítimo + ataques de reventa,
# mide la recuperación desde fuera, copia resultados, consulta Prometheus, y verifica D-3 (bitácora) y S-1/S-2.
# Uso: run-exp3.sh <n> <semilla>
#   Corrida del plan: 1 min calentamiento + 12 min normal (30 ataques) + 2 min rampa + 10 min pico (10 ataques) a 8.000/min.
#   Humo (≈4 min):    SMOKE=1 run-exp3.sh 0 1
# Requisitos: activar-exp3.sh ya ejecutado (imagen 1.1 y TAQ_DETECCION=on) y túneles abiertos (04-acceso.sh + acceso-exp3.sh).
set -euo pipefail
N=${1:?numero}; SEMILLA=${2:?semilla}
if [ "${SMOKE:-0}" = "1" ]; then
  WARM=${WARM_S:-15}; NORMAL=${NORMAL_S:-60}; RAMPA=${RAMPA_S:-20}; PICO=${PICO_S:-45}; AT_N=${ATAQUES_NORMAL:-3}; AT_P=${ATAQUES_PICO:-2}; BOTS=${BOTS:-20}; TASA_PICO=${TASA_PICO:-2000}; HILOS=${HILOS:-200}
else
  WARM=${WARM_S:-60}; NORMAL=${NORMAL_S:-720}; RAMPA=${RAMPA_S:-120}; PICO=${PICO_S:-600}; AT_N=${ATAQUES_NORMAL:-30}; AT_P=${ATAQUES_PICO:-10}; BOTS=${BOTS:-100}; TASA_PICO=${TASA_PICO:-8000}; HILOS=${HILOS:-600}
fi
BOT_MIN=${BOT_POR_MIN:-10}; DUR_ATAQUE=${DURACION_MAX_ATAQUE_S:-60}
AQUI="$(cd "$(dirname "$0")" && pwd)"; EXP3="$(dirname "$AQUI")"; EXPS="$(cd "$EXP3/.." && pwd)"
SALIDA="$EXPS/exp3/resultados/corrida-$N"; mkdir -p "$SALIDA"
export JAVA_HOME=${JAVA_HOME:-/opt/homebrew/opt/openjdk@21}
TOTAL=$((WARM+NORMAL+RAMPA+PICO))
echo "[1/8] Reiniciando estado (reservas, auditoría, colas, cuentas revocadas, bloqueos)"; "$AQUI/reiniciar-estado-exp3.sh"
"$EXPS/exp2/aws/scripts/04-acceso.sh" >/dev/null; "$AQUI/acceso-exp3.sh"
until curl -sf localhost:30090/actuator/health >/dev/null && curl -sf localhost:30091/actuator/health >/dev/null && curl -sf localhost:30092/actuator/health >/dev/null; do sleep 2; done
echo "      reglas antifraude vigentes: $(curl -s localhost:30091/parametros)"
echo "[2/8] Calentando el generador (scripts Groovy actualizados al pod jmeter)"
POD=$(kubectl -n taq get pod -l app=jmeter -o jsonpath='{.items[0].metadata.name}')
for f in init.groovy hilo.groovy; do kubectl -n taq cp "$EXPS/exp1/carga/$f" "$POD:/carga/$f" -c jmeter; done
PARAR="$SALIDA/.parar-medicion"; rm -f "$PARAR"
echo "[3/8] Medición independiente de S-2 (consulta el estado cada pocos ms)"
python3 "$EXP3/scripts/medir_recuperacion.py" "$SALIDA/recuperacion_medida.json" --paso-ms 5 --archivo-parar "$PARAR" --hasta-epoch $(( $(date +%s) + TOTAL + 200 )) >"$SALIDA/medir_recuperacion.log" 2>&1 &
MEDIDOR=$!
echo "[4/8] Carga con JMeter (semilla $SEMILLA): ${WARM}s calentamiento + ${NORMAL}s normal [$AT_N ataques] + ${RAMPA}s rampa + ${PICO}s pico a $TASA_PICO/min [$AT_P ataques]; $BOTS bots x ataque a $BOT_MIN/min"
kubectl -n taq exec deploy/jmeter -- sh -c "rm -rf /resultados/*; jmeter -n -t /carga/plan-exp1.jmx -Jdir=/carga -Jsemilla=$SEMILLA \
  -Jcalentamiento_s=$((WARM+NORMAL)) -Jtrafico_s=$((RAMPA+PICO)) -Jperfil=rampa -Jrampa_s=$RAMPA -Jtasa_pico=$TASA_PICO -Jdescuenta_conflictos=true \
  -Jataques_normal=$AT_N -Jataques_pico=$AT_P -Jbots_por_ataque=$BOTS -Jsolicitudes_bot_por_min=$BOT_MIN -Jduracion_max_ataque_s=$DUR_ATAQUE -Jataque_normal_desde_s=$WARM \
  -Jhilos=$HILOS -Jhost=nodo-entrada:8080 -Jttl_s=480 -Jbitacora=/resultados/bitacora.csv -Jejecucion_json=/resultados/ejecucion.json \
  -l /resultados/jmeter.jtl -j /resultados/jmeter.log" 2>&1 | grep -E "summary =|Starting|end of run" || true
sleep 20
touch "$PARAR"; wait $MEDIDOR || true; rm -f "$PARAR"
echo "[5/8] Copiando resultados del generador"
kubectl -n taq cp "$POD:/resultados" "$SALIDA" -c jmeter
echo "[6/8] Verificación D-3 sobre las reservas legítimas y de bots (verificador de EXP-1)"
mkdir -p "$SALIDA/d3"; set +e
"$JAVA_HOME/bin/java" -Dloader.main=co.uniandes.taq.verificador.Verificador -cp "$EXPS/plataforma/target/taq.jar" \
  org.springframework.boot.loader.launch.PropertiesLauncher "$SALIDA/bitacora.csv" "$SALIDA/d3" http://localhost:30090 jdbc:postgresql://localhost:30432/taq 480 >/dev/null 2>&1
D3=$?
echo "[7/8] Verificación S-1/S-2 (bitácora x bd_auditoria x estado final x Prometheus)"
python3 "$EXP3/scripts/verificar_exp3.py" "$SALIDA"
VER=$?; set -e
echo "[8/8] Evidencia de Grafana"
curl -sf -u "admin:$(cat "$EXPS/exp2/aws/.grafana-pass")" localhost:30300/api/dashboards/uid/exp3asr > "$SALIDA/tablero-grafana.json" || true
echo "Listo: $SALIDA (D-3: $D3, S-1/S-2: $VER; 0 = cumple)"
