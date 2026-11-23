#!/usr/bin/env bash
# Construye (arm64) y publica en ECR las 3 imágenes: plataforma, jmeter y panel.
set -euo pipefail
source "$(dirname "$0")/00-config.sh"
"$EXPS/.venv/bin/python" "$AQUI_AWS/scripts/ecr.py" crear-y-login
( cd "$EXPS/plataforma" && mvn -q -DskipTests package )
docker build --platform linux/arm64 -t $ECR/taq-plataforma:1.0 "$EXPS/plataforma"
docker build --platform linux/arm64 -t $ECR/taq-jmeter:1.0 -f "$AQUI_AWS/imagenes/Dockerfile.jmeter" "$EXPS"
docker build --platform linux/arm64 -t $ECR/taq-panel:1.0 -f "$AQUI_AWS/imagenes/Dockerfile.panel" "$EXPS"
for r in taq-plataforma taq-jmeter taq-panel; do docker push $ECR/$r:1.0; done
