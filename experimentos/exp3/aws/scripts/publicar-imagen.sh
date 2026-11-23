#!/usr/bin/env bash
# Construye (arm64) y publica SOLO la imagen taq-plataforma:$TAG (con detección y respuesta). No toca otras etiquetas ni las imágenes de jmeter/panel.
# Uso: TAG=1.3 ./publicar-imagen.sh   (TAG por defecto 1.3; activar-exp3.sh usa el mismo valor por defecto)
# El generador de carga no necesita imagen nueva: run-exp3.sh copia al pod 'jmeter' los scripts Groovy actualizados.
set -euo pipefail
TAG=${TAG:-1.3}
source "$(dirname "$0")/../../../exp2/aws/scripts/00-config.sh"
"$EXPS/.venv/bin/python" "$EXPS/exp2/aws/scripts/ecr.py" crear-y-login
( cd "$EXPS/plataforma" && mvn -q -DskipTests package )
docker build --platform linux/arm64 -t "$ECR/taq-plataforma:$TAG" "$EXPS/plataforma"
docker push "$ECR/taq-plataforma:$TAG"
