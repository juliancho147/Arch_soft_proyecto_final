#!/usr/bin/env bash
# Copia robusta de un archivo grande desde el pod de JMeter: lo comprime, lo parte en trozos de 500 KB, verifica el md5 de cada trozo
# (con reintentos) y el md5 del archivo final. `kubectl cp` y `kubectl exec cat` se cortan en silencio con archivos grandes.
# Uso: copiar_pod.sh <archivo_remoto> <archivo_local>
set -euo pipefail
REMOTO=${1:?archivo remoto}; LOCAL=${2:?archivo local}
KX="kubectl -n taq exec deploy/jmeter --"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
MD5_REMOTO=$($KX md5sum "$REMOTO" | awk '{print $1}')
$KX sh -c "cd /tmp && rm -f cp_part_* cp.gz && gzip -c '$REMOTO' > cp.gz && split -b 500000 cp.gz cp_part_ && md5sum cp_part_*" > "$TMP/partes.txt"
while read -r esperado parte; do
  ok=0
  for i in 1 2 3 4 5 6 7 8; do
    $KX cat "/tmp/$parte" > "$TMP/$parte" 2>/dev/null || true
    if [ "$(md5 -q "$TMP/$parte" 2>/dev/null || md5sum "$TMP/$parte" | awk '{print $1}')" = "$esperado" ]; then ok=1; break; fi
    sleep 2
  done
  [ $ok = 1 ] || { echo "ERROR: no se pudo copiar $parte" >&2; exit 1; }
done < "$TMP/partes.txt"
cat "$TMP"/cp_part_* | gunzip > "$LOCAL"
MD5_LOCAL=$(md5 -q "$LOCAL" 2>/dev/null || md5sum "$LOCAL" | awk '{print $1}')
[ "$MD5_LOCAL" = "$MD5_REMOTO" ] || { echo "ERROR: md5 distinto en $LOCAL" >&2; exit 1; }
$KX sh -c "rm -f /tmp/cp_part_* /tmp/cp.gz" || true
echo "copiado y verificado: $LOCAL"
