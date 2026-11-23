# Variables comunes. Se carga con: source scripts/00-config.sh
export AWS_REGION=${AWS_REGION:-us-east-1}
export CLUSTER=taq-exp
AQUI_AWS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AQUI_AWS
export EXPS="$(cd "$AQUI_AWS/../.." && pwd)"          # carpeta experimentos/
export ACCOUNT_ID=${ACCOUNT_ID:-$("$EXPS/.venv/bin/python" -c "import boto3;print(boto3.client('sts').get_caller_identity()['Account'])")}
export ECR="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
export JAVA_HOME=${JAVA_HOME:-/opt/homebrew/opt/openjdk@21}
