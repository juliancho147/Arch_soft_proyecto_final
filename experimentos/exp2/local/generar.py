#!/usr/bin/env python3
"""Perfil LOCAL de EXP-2 (kind, una sola máquina): tope de 5 réplicas por pod, memoria ajustada y observabilidad por pod.
Genera: 10-plataforma-local.yaml, 20-observabilidad-local.yaml, 30-tableros-local.yaml"""
import json, os, pathlib, re, subprocess, sys
AQUI = pathlib.Path(__file__).parent; EXPS = AQUI.parents[1]
MAXR = {"nodo-entrada": 5, "nodo-reserva": 5, "nodo-pasarela": 3}      # pasarela en 3 para dejar memoria al resto
ENV = """            - { name: TAQ_REDIS_URL, value: "redis://redis:6379" }
            - { name: TAQ_BLOQUEO_URL, value: "http://bd-bloqueo:8080" }
            - { name: TAQ_RESERVA_URL, value: "http://nodo-reserva:8080" }
            - { name: TAQ_PASARELA_URL, value: "http://nodo-pasarela:8080" }
            - { name: TAQ_DB_URL, value: "jdbc:postgresql://postgres:5432/taq" }"""
def dep(n, rol, heap, req, lim, mem, extra="", ext_port=None):
    s = f"""apiVersion: apps/v1
kind: Deployment
metadata: {{ name: {n}, namespace: taq }}
spec:
  replicas: 1
  selector: {{ matchLabels: {{ app: {n} }} }}
  template:
    metadata: {{ labels: {{ app: {n}, taq-metricas: "true" }} }}
    spec:
      terminationGracePeriodSeconds: 20
      containers:
        - name: {n}
          image: taq/plataforma:1.0
          imagePullPolicy: Never
          ports: [{{ name: http, containerPort: 8080 }}]
          env:
            - {{ name: TAQ_ROLE, value: "{rol}" }}
            - {{ name: JAVA_OPTS, value: "-Xmx{heap}m -XX:+UseG1GC" }}
{ENV}
{extra}          readinessProbe: {{ httpGet: {{ path: /actuator/health, port: http }}, initialDelaySeconds: 10, periodSeconds: 3 }}
          resources: {{ requests: {{ cpu: {req}, memory: 256Mi }}, limits: {{ cpu: "{lim}", memory: {mem} }} }}
---
apiVersion: v1
kind: Service
metadata: {{ name: {n}, namespace: taq, labels: {{ app: {n} }} }}
spec: {{ selector: {{ app: {n} }}, ports: [{{ name: http, port: 8080, targetPort: http }}] }}
---
"""
    if ext_port:
        s += f"""apiVersion: v1
kind: Service
metadata: {{ name: {n}-ext, namespace: taq }}
spec: {{ type: NodePort, selector: {{ app: {n} }}, ports: [{{ port: 8080, nodePort: {ext_port} }}] }}
---
"""
    return s
def hpa(n):
    return f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: {{ name: {n}, namespace: taq }}
spec:
  scaleTargetRef: {{ apiVersion: apps/v1, kind: Deployment, name: {n} }}
  minReplicas: 1
  maxReplicas: {MAXR[n]}
  metrics: [{{ type: Resource, resource: {{ name: cpu, target: {{ type: Utilization, averageUtilization: 60 }} }} }}]
  behavior:
    scaleUp:   {{ stabilizationWindowSeconds: 0,   policies: [{{ type: Pods, value: 2, periodSeconds: 15 }}], selectPolicy: Max }}
    scaleDown: {{ stabilizationWindowSeconds: 300, policies: [{{ type: Pods, value: 1, periodSeconds: 60 }}] }}
---
"""
y = dep("nodo-entrada", "gateway", 256, "400m", 2, "512Mi", ext_port=30080)
y += dep("nodo-reserva", "reserva", 256, "400m", 2, "512Mi", extra='            - { name: TAQ_WORKERS, value: "16" }\n')
y += dep("nodo-pasarela", "pasarela", 128, "200m", 1, "320Mi")
y += dep("bd-bloqueo", "bloqueo", 640, "250m", 1, "896Mi", ext_port=30090)   # guarda estado y auditoría en memoria: crece con el pico
y += "".join(hpa(n) for n in MAXR)
(AQUI / "10-plataforma-local.yaml").write_text(y.rstrip("-\n") + "\n")

(AQUI / "20-observabilidad-local.yaml").write_text("""apiVersion: v1
kind: ServiceAccount
metadata: { name: prometheus, namespace: taq }
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: { name: prometheus-taq }
rules: [{ apiGroups: [""], resources: [pods], verbs: [get, list, watch] }]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: { name: prometheus-taq }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: prometheus-taq }
subjects: [{ kind: ServiceAccount, name: prometheus, namespace: taq }]
---
apiVersion: v1
kind: ConfigMap
metadata: { name: prom-config, namespace: taq }
data:
  prometheus.yml: |
    global: { scrape_interval: 5s, evaluation_interval: 5s }
    scrape_configs:
      - job_name: taq
        metrics_path: /actuator/prometheus
        kubernetes_sd_configs: [{ role: pod, namespaces: { names: [taq] } }]
        relabel_configs:
          - { source_labels: [__meta_kubernetes_pod_label_taq_metricas], action: keep, regex: "true" }
          - { source_labels: [__meta_kubernetes_pod_ip], target_label: __address__, replacement: "$1:8080" }
          - { source_labels: [__meta_kubernetes_pod_name], target_label: pod }
      - job_name: kube-state-metrics
        static_configs: [{ targets: ["kube-state-metrics:8080"] }]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: { name: ksm-taq }
rules:
  - { apiGroups: [""], resources: [pods, nodes, namespaces], verbs: [list, watch] }
  - { apiGroups: [apps], resources: [deployments, replicasets], verbs: [list, watch] }
  - { apiGroups: [autoscaling], resources: [horizontalpodautoscalers], verbs: [list, watch] }
---
apiVersion: v1
kind: ServiceAccount
metadata: { name: kube-state-metrics, namespace: taq }
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata: { name: ksm-taq }
roleRef: { apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: ksm-taq }
subjects: [{ kind: ServiceAccount, name: kube-state-metrics, namespace: taq }]
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: kube-state-metrics, namespace: taq }
spec:
  replicas: 1
  selector: { matchLabels: { app: kube-state-metrics } }
  template:
    metadata: { labels: { app: kube-state-metrics } }
    spec:
      serviceAccountName: kube-state-metrics
      containers:
        - name: ksm
          image: registry.k8s.io/kube-state-metrics/kube-state-metrics:v2.13.0
          args: ["--resources=deployments,horizontalpodautoscalers,pods,nodes"]
          ports: [{ containerPort: 8080 }]
          resources: { requests: { cpu: 20m, memory: 32Mi }, limits: { memory: 96Mi } }
---
apiVersion: v1
kind: Service
metadata: { name: kube-state-metrics, namespace: taq }
spec: { selector: { app: kube-state-metrics }, ports: [{ port: 8080 }] }
""")

# Tableros: EXP-1 + EXP-2 (local) en el mismo ConfigMap que ya monta Grafana
env = dict(os.environ, LOCAL="1", MAXR="5", CPU_REQ="0.4")
subprocess.run([sys.executable, str(EXPS / "exp2/aws/dashboards/gen-dashboard-exp2.py")], env=env, check=True, capture_output=True)
d1 = json.loads((EXPS / "exp1/k8s/30-grafana-dashboard.json").read_text())["data"]["exp1.json"]
d2 = json.loads((EXPS / "exp2/aws/dashboards/exp2-dashboard-local.yaml").read_text())["data"]["exp2.json"]
(AQUI / "30-tableros-local.yaml").write_text(json.dumps({"apiVersion": "v1", "kind": "ConfigMap",
    "metadata": {"name": "grafana-dash", "namespace": "taq"}, "data": {"exp1.json": d1, "exp2.json": d2}}))
print("generado en", AQUI)
