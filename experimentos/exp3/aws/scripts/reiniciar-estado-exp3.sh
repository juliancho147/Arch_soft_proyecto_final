#!/usr/bin/env bash
# Deja el sistema en cero entre ejecuciones de EXP-3: reservas, tablas de seguridad, colas, cuentas revocadas/marcadas y bloqueos.
# Conserva parametros_antifraude (las reglas elegidas). Reinicia también detección y respuesta (recrean sus tablas al arrancar).
set -euo pipefail
kubectl -n taq exec deploy/postgres -- psql -U taq -d taq -qc "TRUNCATE reserva_log RESTART IDENTITY; DROP TABLE IF EXISTS auditoria_seguridad, cuenta_revocada, orden_cancelada"
kubectl -n taq exec deploy/redis -- sh -c 'redis-cli --scan --pattern "cola_*" | xargs -r redis-cli del >/dev/null; redis-cli del cuentas_revocadas cuentas_marcadas >/dev/null; true'
kubectl -n taq rollout restart deploy/bd-bloqueo deploy/nodo-entrada deploy/nodo-reserva deploy/nodo-pasarela deploy/deteccion deploy/respuesta
for d in bd-bloqueo nodo-entrada nodo-reserva nodo-pasarela deteccion respuesta; do kubectl -n taq rollout status deploy/$d --timeout=300s; done
echo "Esperando a que el autoescalador regrese a 1 réplica…"; sleep 20
