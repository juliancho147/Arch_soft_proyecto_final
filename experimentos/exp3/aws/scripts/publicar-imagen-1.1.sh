#!/usr/bin/env bash
# Construye (arm64) y publica SOLO la imagen taq-plataforma:1.1 (con detección y respuesta). No toca la 1.0 ni las imágenes de jmeter/panel.
# El generador de carga no necesita imagen nueva: run-exp3.sh copia al pod 'jmeter' los scripts Groovy actualizados.
set -euo pipefail
source "$(dirname "$0")/../../../exp2/aws/scripts/00-config.sh"
"$EXPS/.venv/bin/python" "$EXPS/exp2/aws/scripts/ecr.py" crear-y-login
( cd "$EXPS/plataforma" && mvn -q -DskipTests package )
docker build --platform linux/arm64 -t "$ECR/taq-plataforma:1.1" "$EXPS/plataforma"
docker push "$ECR/taq-plataforma:1.1"
