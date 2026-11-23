#!/usr/bin/env bash
# Crea el clúster EKS y le instala monitoreo y autoescalador de nodos. COBRA DESDE QUE SE EJECUTA (~USD 0,9–1,6 por hora).
set -euo pipefail
source "$(dirname "$0")/00-config.sh"
for h in eksctl helm kubectl docker; do command -v $h >/dev/null || { echo "Falta $h"; exit 1; }; done
echo "Cuenta: $ACCOUNT_ID · región: $AWS_REGION · clúster: $CLUSTER"
[ "${1:-}" = "-y" ] || { read -r -p "Esto crea recursos que cuestan dinero. ¿Continuar? [s/N] " r; [ "$r" = "s" ] || exit 1; }
eksctl create cluster -f "$AQUI_AWS/eksctl-cluster.yaml"
eksctl utils write-kubeconfig --cluster $CLUSTER --region $AWS_REGION
kubectl apply -f - <<SC
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata: { name: gp3 }
provisioner: ebs.csi.aws.com
parameters: { type: gp3 }
volumeBindingMode: WaitForFirstConsumer
SC
helm repo add autoscaler https://kubernetes.github.io/autoscaler >/dev/null
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update >/dev/null
helm upgrade --install cluster-autoscaler autoscaler/cluster-autoscaler -n kube-system \
  --set autoDiscovery.clusterName=$CLUSTER --set awsRegion=$AWS_REGION --set image.tag=v1.31.0 \
  --set nodeSelector.rol=sistema --set extraArgs.balance-similar-node-groups=true --set extraArgs.scale-down-unneeded-time=3m
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
GRAFANA_PASS=$(openssl rand -base64 12)
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack -n monitoring \
  -f "$AQUI_AWS/helm-values-monitoreo.yaml" --set grafana.adminPassword="$GRAFANA_PASS" --wait --timeout 10m
echo "$GRAFANA_PASS" > "$AQUI_AWS/.grafana-pass"; chmod 600 "$AQUI_AWS/.grafana-pass"
echo "Listo. Contraseña de Grafana (usuario admin) en $AQUI_AWS/.grafana-pass"
