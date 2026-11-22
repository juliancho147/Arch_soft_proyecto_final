#!/usr/bin/env bash
# Las 3 corridas oficiales de EXP-1, una tras otra, con semillas distintas.
set -uo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
for n in 1 2 3; do "$AQUI/run.sh" "$n" "$n"; done  # se lanza con: caffeinate -i run-todas.sh
echo "TODAS LISTAS"
