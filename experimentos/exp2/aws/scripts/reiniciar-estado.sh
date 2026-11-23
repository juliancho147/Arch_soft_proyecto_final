#!/usr/bin/env bash
# Deja el sistema en cero entre ejecuciones: BD de reservas, colas, bloqueos y contadores; vuelve a 1 réplica.
set -euo pipefail
kubectl -n taq exec deploy/postgres -- psql -U taq -d taq -qc "TRUNCATE reserva_log RESTART IDENTITY"
kubectl -n taq exec deploy/redis -- sh -c 'redis-cli --scan --pattern "cola_*" | xargs -r redis-cli del >/dev/null; true'
kubectl -n taq rollout restart deploy/bd-bloqueo deploy/nodo-entrada deploy/nodo-reserva deploy/nodo-pasarela
for d in bd-bloqueo nodo-entrada nodo-reserva nodo-pasarela; do kubectl -n taq rollout status deploy/$d --timeout=300s; done
echo "Esperando a que el autoescalador regrese a 1 réplica…"; sleep 20
