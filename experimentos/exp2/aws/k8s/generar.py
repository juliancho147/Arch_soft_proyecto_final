#!/usr/bin/env python3
"""Genera los manifiestos de EXP-2 para EKS en k8s/*.yaml. Uso: ECR=<cuenta>.dkr.ecr.us-east-1.amazonaws.com python3 generar.py"""
import os, pathlib
ECR = os.environ.get("ECR", "<ECR>")
AQUI = pathlib.Path(__file__).parent
IMG = f"{ECR}/taq-plataforma:1.0"
ENV_COMUN = """            - { name: TAQ_REDIS_URL, value: "redis://redis:6379" }
            - { name: TAQ_BLOQUEO_URL, value: "http://bd-bloqueo:8080" }
            - { name: TAQ_RESERVA_URL, value: "http://nodo-reserva:8080" }
            - { name: TAQ_PASARELA_URL, value: "http://nodo-pasarela:8080" }
            - { name: TAQ_DB_URL, value: "jdbc:postgresql://postgres:5432/taq" }"""

def despliegue(nombre, rol, heap, cpu_req, cpu_lim, mem_lim, rol_nodo, extra_env="", replicas=1, antiafin=False):
    spread = """      topologySpreadConstraints:
        - { maxSkew: 1, topologyKey: kubernetes.io/hostname, whenUnsatisfiable: ScheduleAnyway, labelSelector: { matchLabels: { app: %s } } }
""" % nombre if antiafin else ""
    return f"""apiVersion: apps/v1
kind: Deployment
metadata: {{ name: {nombre}, namespace: taq }}
spec:
  replicas: {replicas}
  selector: {{ matchLabels: {{ app: {nombre} }} }}
  template:
    metadata:
      labels: {{ app: {nombre}, taq-metricas: "true" }}
    spec:
      nodeSelector: {{ rol: {rol_nodo}, kubernetes.io/arch: arm64 }}
{spread}      terminationGracePeriodSeconds: 20
      containers:
        - name: {nombre}
          image: {IMG}
          imagePullPolicy: IfNotPresent
          ports: [{{ name: http, containerPort: 8080 }}]
          env:
            - {{ name: TAQ_ROLE, value: "{rol}" }}
            - {{ name: JAVA_OPTS, value: "-Xmx{heap}m -XX:+UseG1GC" }}
{ENV_COMUN}
{extra_env}          readinessProbe: {{ httpGet: {{ path: /actuator/health, port: http }}, initialDelaySeconds: 15, periodSeconds: 3 }}
          resources: {{ requests: {{ cpu: {cpu_req}, memory: 384Mi }}, limits: {{ cpu: "{cpu_lim}", memory: {mem_lim} }} }}
---
apiVersion: v1
kind: Service
metadata: {{ name: {nombre}, namespace: taq, labels: {{ app: {nombre} }} }}
spec: {{ selector: {{ app: {nombre} }}, ports: [{{ name: http, port: 8080, targetPort: http }}] }}
---
"""

def hpa(nombre, maxr=8):
    return f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: {{ name: {nombre}, namespace: taq }}
spec:
  scaleTargetRef: {{ apiVersion: apps/v1, kind: Deployment, name: {nombre} }}
  minReplicas: 1
  maxReplicas: {maxr}
  metrics:
    - type: Resource
      resource: {{ name: cpu, target: {{ type: Utilization, averageUtilization: 60 }} }}
  behavior:
    scaleUp:   {{ stabilizationWindowSeconds: 0,   policies: [{{ type: Pods, value: 4, periodSeconds: 15 }}, {{ type: Percent, value: 100, periodSeconds: 15 }}], selectPolicy: Max }}
    scaleDown: {{ stabilizationWindowSeconds: 300, policies: [{{ type: Pods, value: 1, periodSeconds: 60 }}] }}
---
"""

plataforma = ""
plataforma += despliegue("nodo-entrada", "gateway", 320, "500m", 2, "640Mi", "app", antiafin=True)
plataforma += despliegue("nodo-reserva", "reserva", 320, "500m", 2, "640Mi", "app",
                         extra_env='            - { name: TAQ_WORKERS, value: "16" }\n', antiafin=True)
plataforma += despliegue("nodo-pasarela", "pasarela", 192, "250m", 1, "512Mi", "app", antiafin=True)
plataforma += despliegue("bd-bloqueo", "bloqueo", 256, "1000m", 2, "512Mi", "sistema")   # un solo hilo: no escala, tiene su propio nodo estable
plataforma += hpa("nodo-entrada") + hpa("nodo-reserva") + hpa("nodo-pasarela")
(AQUI / "10-plataforma.yaml").write_text(plataforma.rstrip("-\n") + "\n")

# Datos: se reutiliza el manifiesto de EXP-1 (esquema, 130.000 asientos) fijándolo al grupo de nodos 'sistema'.
datos = (AQUI.parents[2] / "exp1/k8s/00-datos.yaml").read_text()
datos = datos.replace("    spec:\n      containers:", "    spec:\n      nodeSelector: { rol: sistema, kubernetes.io/arch: arm64 }\n      containers:")
datos = "\n".join(l for l in datos.split("\n") if "nodePort" not in l or "Service" in l)   # sin NodePort: se accede por port-forward
import re
datos = re.sub(r"apiVersion: v1\nkind: Service\nmetadata: \{ name: postgres-ext.*?\n---\n", "", datos, flags=re.S)
(AQUI / "00-datos.yaml").write_text(datos)

# Monitoreo: PodMonitor para que Prometheus descubra cada réplica (el scrape estático de EXP-1 no sirve con N réplicas).
(AQUI / "20-podmonitor.yaml").write_text("""apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata: { name: taq, namespace: monitoring, labels: { release: kube-prometheus-stack } }
spec:
  namespaceSelector: { matchNames: [taq] }
  selector: { matchLabels: { taq-metricas: "true" } }
  podMetricsEndpoints:
    - { port: http, path: /actuator/prometheus, interval: 5s }
""")

# Generador de carga: JMeter (para las ejecuciones oficiales) y panel de inyección, ambos en el nodo 'carga'.
(AQUI / "30-carga.yaml").write_text(f"""apiVersion: apps/v1
kind: Deployment
metadata: {{ name: jmeter, namespace: taq }}
spec:
  replicas: 1
  selector: {{ matchLabels: {{ app: jmeter }} }}
  template:
    metadata: {{ labels: {{ app: jmeter }} }}
    spec:
      nodeSelector: {{ rol: carga }}
      tolerations: [{{ key: rol, operator: Equal, value: carga, effect: NoSchedule }}]
      containers:
        - name: jmeter
          image: {ECR}/taq-jmeter:1.0
          command: ["sleep", "infinity"]
          env: [{{ name: JVM_ARGS, value: "-Xms2g -Xmx3g" }}]
          resources: {{ requests: {{ cpu: "3", memory: 4Gi }} }}
---
apiVersion: apps/v1
kind: Deployment
metadata: {{ name: panel, namespace: taq }}
spec:
  replicas: 1
  selector: {{ matchLabels: {{ app: panel }} }}
  template:
    metadata: {{ labels: {{ app: panel }} }}
    spec:
      serviceAccountName: panel
      nodeSelector: {{ rol: carga }}
      tolerations: [{{ key: rol, operator: Equal, value: carga, effect: NoSchedule }}]
      containers:
        - name: panel
          image: {ECR}/taq-panel:1.0
          imagePullPolicy: Always
          ports: [{{ containerPort: 8088 }}]
          env:
            - {{ name: TAQ_GATEWAY, value: "http://nodo-entrada:8080" }}
            - {{ name: TAQ_PROM, value: "http://kube-prometheus-stack-prometheus.monitoring:9090" }}
          resources: {{ requests: {{ cpu: 500m, memory: 256Mi }} }}
---
apiVersion: v1
kind: ServiceAccount
metadata: {{ name: panel, namespace: taq }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: {{ name: panel, namespace: taq }}
rules:
  - {{ apiGroups: [""], resources: [pods], verbs: [get, list] }}
  - {{ apiGroups: [""], resources: [pods/exec], verbs: [create] }}
  - {{ apiGroups: [apps], resources: [deployments], verbs: [get, list, patch] }}
  - {{ apiGroups: [apps], resources: [deployments/scale], verbs: [get, patch, update] }}
  - {{ apiGroups: [autoscaling], resources: [horizontalpodautoscalers], verbs: [get, list, patch] }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {{ name: panel, namespace: taq }}
roleRef: {{ apiGroup: rbac.authorization.k8s.io, kind: Role, name: panel }}
subjects: [{{ kind: ServiceAccount, name: panel, namespace: taq }}]
---
apiVersion: v1
kind: Service
metadata: {{ name: panel, namespace: taq }}
spec: {{ selector: {{ app: panel }}, ports: [{{ port: 8088 }}] }}
""")
print("manifiestos generados en", AQUI)
