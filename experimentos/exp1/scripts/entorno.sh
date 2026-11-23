#!/usr/bin/env bash
# Registra las características de la máquina y del clúster, para interpretar los resultados.
AQUI="$(cd "$(dirname "$0")" && pwd)"; EXP="$(dirname "$AQUI")"
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
SAL="$EXP/resultados/entorno.md"; mkdir -p "$EXP/resultados"
{
echo "# Entorno de ejecución de EXP-1"
echo
echo "| Dato | Valor |"; echo "|---|---|"
echo "| Fecha del registro | $(date '+%Y-%m-%d %H:%M %Z') |"
echo "| Máquina | $(sysctl -n machdep.cpu.brand_string 2>/dev/null || uname -m), $(sysctl -n hw.ncpu) núcleos, $(( $(sysctl -n hw.memsize) / 1073741824 )) GB de RAM |"
echo "| Sistema operativo | $(sw_vers -productName) $(sw_vers -productVersion) |"
echo "| Docker (CPUs / memoria asignadas) | $(docker info --format '{{.NCPU}} CPUs / {{.MemTotal}} bytes' 2>/dev/null | awk '{printf "%s CPUs / %.1f GiB", $1, $4/1073741824}') |"
echo "| Kubernetes local | kind $(kind version | awk '{print $2}') con 1 nodo (\`kind-taq\`), kubectl $(kubectl version --client -o json | python3 -c 'import sys,json;print(json.load(sys.stdin)["clientVersion"]["gitVersion"])') |"
echo "| JMeter | $(jmeter --version 2>&1 | grep -Eo '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1) (en la máquina anfitriona, fuera del clúster) |"
echo "| JDK de compilación / JRE de ejecución | $($JAVA_HOME/bin/java -version 2>&1 | head -1 | awk -F'"' '{print $2}') (--release 17) / Temurin 17 en los pods |"
echo "| Commit del código | $(git -C "$EXP" rev-parse --short HEAD) (rama $(git -C "$EXP" branch --show-current)) |"
echo
echo "## Pods y límites de recursos"
echo
echo "| Pod | Réplicas | CPU (solicitud / límite) | Memoria (solicitud / límite) |"; echo "|---|---|---|---|"
kubectl -n taq get deploy -o json | python3 "$AQUI/_pods.py"
echo
echo "Todo comparte la misma máquina: clúster, JMeter, Prometheus y Grafana. Las cifras de latencia incluyen esa competencia por recursos."
} > "$SAL"
echo "escrito $SAL"
