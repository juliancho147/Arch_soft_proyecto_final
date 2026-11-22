#!/usr/bin/env python3
"""Genera los manifiestos de EXP-3 para EKS (solo los genera; no despliega nada).
Uso: ECR=<cuenta>.dkr.ecr.us-east-1.amazonaws.com python3 generar_exp3.py

  10-plataforma-exp3.yaml  : nodo-entrada y bd-bloqueo con la imagen 1.1 y TAQ_DETECCION=on (el resto de la plataforma no cambia)
  20-deteccion-respuesta.yaml : pods nuevos 'deteccion' y 'respuesta' (misma imagen 1.1, nodo del grupo 'sistema')

Los pods llevan el label taq-metricas: "true" y el puerto http 8080, así que el PodMonitor de EXP-2 los descubre sin cambios.
Para volver a EXP-1/EXP-2: kubectl apply -f ../../../exp2/aws/k8s/10-plataforma.yaml (imagen 1.0, sin TAQ_DETECCION) y borrar los dos pods nuevos."""
import os, pathlib
ECR = os.environ.get("ECR", "<ECR>")
AQUI = pathlib.Path(__file__).parent
IMG = f"{ECR}/taq-plataforma:1.1"
ENV_COMUN = """            - { name: TAQ_REDIS_URL, value: "redis://redis:6379" }
            - { name: TAQ_BLOQUEO_URL, value: "http://bd-bloqueo:8080" }
            - { name: TAQ_RESERVA_URL, value: "http://nodo-reserva:8080" }
            - { name: TAQ_PASARELA_URL, value: "http://nodo-pasarela:8080" }
            - { name: TAQ_DB_URL, value: "jdbc:postgresql://postgres:5432/taq" }"""

def despliegue(nombre, rol, heap, cpu_req, cpu_lim, mem_lim, rol_nodo, extra_env="", antiafin=False):
    # Misma plantilla que exp2/aws/k8s/generar.py, con la imagen 1.1.
    spread = """      topologySpreadConstraints:
        - { maxSkew: 1, topologyKey: kubernetes.io/hostname, whenUnsatisfiable: ScheduleAnyway, labelSelector: { matchLabels: { app: %s } } }
""" % nombre if antiafin else ""
    return f"""apiVersion: apps/v1
kind: Deployment
metadata: {{ name: {nombre}, namespace: taq }}
spec:
  replicas: 1
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

ON = '            - { name: TAQ_DETECCION, value: "on" }\n'
# Gateway y bd_bloqueo: mismos recursos que en EXP-2, ahora con detección encendida.
base = despliegue("nodo-entrada", "gateway", 320, "500m", 2, "640Mi", "app", extra_env=ON, antiafin=True)
base += despliegue("bd-bloqueo", "bloqueo", 256, "1000m", 2, "512Mi", "sistema", extra_env=ON)
(AQUI / "10-plataforma-exp3.yaml").write_text(base.rstrip("-\n") + "\n")

# Pods nuevos. Detector: 4 hilos de consumo (cada uno con su conexión a Redis y Postgres). Respuesta: 4 hilos.
nuevos = despliegue("deteccion", "deteccion", 320, "500m", 2, "640Mi", "sistema",
                    extra_env=ON + '            - { name: TAQ_DETECCION_HILOS, value: "4" }\n')
nuevos += despliegue("respuesta", "respuesta", 256, "250m", 1, "512Mi", "sistema",
                     extra_env=ON + '            - { name: TAQ_RESPUESTA_HILOS, value: "4" }\n')
(AQUI / "20-deteccion-respuesta.yaml").write_text(nuevos.rstrip("-\n") + "\n")
print("manifiestos de EXP-3 generados en", AQUI)
