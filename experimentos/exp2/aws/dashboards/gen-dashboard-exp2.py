#!/usr/bin/env python3
"""Genera el tablero de EXP-2 (E-1 y D-3) como ConfigMap para el Grafana de kube-prometheus-stack (namespace monitoring)."""
import json, os, pathlib
MAXR = int(os.environ.get("MAXR", "8"))          # tope de réplicas por pod (AWS: 8; local: 5)
LOCAL = bool(os.environ.get("LOCAL"))             # en local no hay cAdvisor: la CPU sale de las métricas de cada JVM
DS = {"type": "prometheus", "uid": "prom"}
panels = []
def add(tipo, titulo, x, y, w, h, targets, unit="short", desc="", thresholds=None, extra=None, opts=None):
    p = {"id": len(panels) + 1, "type": tipo, "title": titulo, "description": desc, "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "datasource": DS, "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
         "targets": [dict(t, refId=chr(65 + i), datasource=DS) for i, t in enumerate(targets)]}
    if thresholds:
        p["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": thresholds}
        p["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
    if extra: p["fieldConfig"]["defaults"].update(extra)
    if opts: p["options"] = opts
    panels.append(p)
def row(t, y): panels.append({"id": len(panels) + 1, "type": "row", "title": t, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "collapsed": False})
last = {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}
LIM = 0.25                       # ASR E-1: p95 < 250 ms
OBJ = 8000 / 60                  # solicitudes/s del pico (≈133)
def sobreumbral(v): return [{"color": "green", "value": None}, {"color": "red", "value": v}]
def linea(v, nombre): return {"expr": f"vector({v})", "legendFormat": nombre}
P95 = 'histogram_quantile(0.95, sum(rate(taq_reservar_seconds_bucket[{w}])) by (le))'
y = 0
row("E-1  Reservar en el pico: p95 < 250 ms sostenido 15 min", y); y += 1
add("stat", "p95 de reservar (último minuto)", 0, y, 4, 6, [{"expr": P95.format(w="1m"), "instant": True}], "s",
    "Verde = cumple E-1 (< 250 ms). Medido en el gateway con todas las réplicas.", sobreumbral(LIM), {"decimals": 3}, last)
add("stat", "Solicitudes/s ahora", 4, y, 4, 6, [{"expr": "sum(rate(taq_reservar_seconds_count[30s]))", "instant": True}], "reqps",
    "Objetivo del pico: ≈133 solicitudes/s (8.000/min).", [{"color": "blue", "value": None}], {"decimals": 0}, last)
add("stat", "Solicitudes recibidas en el rango", 8, y, 4, 6, [{"expr": "sum(taq_reservar_seconds_count) - (sum(taq_reservar_seconds_count offset $__range) or vector(0))", "instant": True}], "short", "", [{"color": "blue", "value": None}], {"decimals": 0}, last)
add("stat", "Rechazos por cola llena", 12, y, 4, 6, [{"expr": "(sum(taq_rechazos_cola_llena_total) or vector(0)) - (sum(taq_rechazos_cola_llena_total offset $__range) or vector(0))", "instant": True}], "short",
    "Solicitudes que no cupieron en la cola acotada. E-1 pide no perder solicitudes: lo esperado es 0.", [{"color": "green", "value": None}, {"color": "red", "value": 1}], None, last)
add("timeseries", "p95 de reservar vs. límite del ASR (250 ms)", 16, y, 8, 6,
    [{"expr": P95.format(w="30s"), "legendFormat": "p95 reservar"}, linea(LIM, "límite ASR 250 ms")], "s"); y += 6
add("timeseries", "Solicitudes por segundo vs. objetivo del pico (rampa y meseta)", 0, y, 12, 7,
    [{"expr": "sum(rate(taq_reservar_seconds_count[30s]))", "legendFormat": "solicitudes/s"}, linea(round(OBJ, 1), "objetivo pico 133/s"),
     {"expr": "sum(rate(taq_rechazos_cola_llena_total[30s])) or vector(0)", "legendFormat": "rechazadas por cola llena/s"}], "reqps")
add("timeseries", "p95 acumulado de la ventana del pico (15 min) y errores", 12, y, 12, 7,
    [{"expr": P95.format(w="15m"), "legendFormat": "p95 últimos 15 min"}, linea(LIM, "límite ASR 250 ms"),
     {"expr": 'sum(rate(taq_reservar_seconds_count{resultado!~"OK|NO_DISPONIBLE"}[30s])) or vector(0)', "legendFormat": "errores técnicos/s"}], "s"); y += 7

row(f"Equilibrio del autoescalado (máximo {MAXR} réplicas por pod; objetivo CPU 60 %)", y); y += 1
add("timeseries", "Réplicas listas por pod", 0, y, 12, 8,
    [{"expr": 'kube_deployment_status_replicas_available{namespace="taq",deployment=~"nodo-.*"}', "legendFormat": "{{deployment}}"}, linea(MAXR, f"máximo {MAXR}")],
    "short", "El experimento observa en cuántas réplicas se estabiliza cada pod.", None, {"decimals": 0, "min": 0, "max": MAXR + 1,
    "custom": {"lineInterpolation": "stepAfter"}})
CPU_REQ = float(os.environ.get("CPU_REQ", "0.5"))     # CPU solicitada por réplica de nodo-entrada / nodo-reserva
CPU_Q = ('avg(rate(process_cpu_time_ns_total{job="taq"}[30s]) / 1e9) by (componente) / %s * 100' % CPU_REQ) if LOCAL else \
        'sum(rate(container_cpu_usage_seconds_total{namespace="taq",container=~"nodo-.*"}[30s])) by (container) / sum(kube_pod_container_resource_requests{namespace="taq",resource="cpu",container=~"nodo-.*"}) by (container) * 100'
add("timeseries", "CPU promedio por pod vs. objetivo (60 % de lo solicitado)", 12, y, 12, 8,
    [{"expr": CPU_Q, "legendFormat": "{{componente}}" if LOCAL else "{{container}}"}, linea(60, "objetivo 60 %")], "percent"); y += 8
add("timeseries", "Réplicas deseadas por el autoescalador (HPA)", 0, y, 12, 6,
    [{"expr": 'kube_horizontalpodautoscaler_status_desired_replicas{namespace="taq"}', "legendFormat": "{{horizontalpodautoscaler}} deseadas"}],
    "short", "", None, {"decimals": 0, "min": 0, "custom": {"lineInterpolation": "stepAfter"}})
add("timeseries", "Nodos del clúster listos", 12, y, 12, 6,
    [{"expr": 'count(kube_node_status_condition{condition="Ready",status="true"})', "legendFormat": "nodos"}],
    "short", "El autoescalador de nodos agrega máquinas cuando los pods no caben.", None, {"decimals": 0, "min": 0}); y += 6

row("Hilo único de bd_bloqueo: ¿es el cuello de botella?", y); y += 1
add("timeseries", "Operaciones por segundo del hilo único", 0, y, 8, 7,
    [{"expr": "sum(rate(taq_bloqueo_ops_total[30s]))", "legendFormat": "operaciones/s"}], "ops")
add("timeseries", "Ocupación del hilo único (% del tiempo)", 8, y, 8, 7,
    [{"expr": "rate(taq_hilo_unico_ocupado_nanos_total[30s])/1e9*100", "legendFormat": "% ocupado"}], "percent", "", None, {"min": 0, "max": 100})
add("timeseries", "Cola de operaciones: profundidad y espera p99", 16, y, 8, 7,
    [{"expr": "max_over_time(taq_cola_operacion_profundidad[15s])", "legendFormat": "solicitudes en cola (máx.)"},
     {"expr": "histogram_quantile(0.99, sum(rate(taq_cola_operacion_espera_seconds_bucket[30s])) by (le))", "legendFormat": "p99 espera (s)"}]); y += 7

row("D-3  Una silla, una sola reserva, también con réplicas compitiendo", y); y += 1
add("timeseries", "Solicitudes simultáneas a una misma silla en el tiempo", 0, y, 15, 8, [{"expr": "taq_conflicto_pico_misma_silla", "legendFormat": "solicitudes a la misma silla"}],
    "short", "Plano en 0 mientras no hay disputa; cada pico es una ráfaga.", None,
    {"min": 0, "decimals": 0, "color": {"mode": "fixed", "fixedColor": "purple"},
     "custom": {"lineInterpolation": "stepAfter", "fillOpacity": 30, "lineWidth": 2, "showPoints": "never"}})
add("timeseries", "Solicitudes en conflicto: aprobadas vs. no aprobadas", 15, y, 9, 8,
    [{"expr": "taq_rafaga_aprobadas", "legendFormat": "aprobadas"}, {"expr": "taq_rafaga_canceladas", "legendFormat": "no aprobadas"}],
    "short", "Última ráfaga (~12 s): 1 verde + el resto rojo = total de la ráfaga.", None,
    {"min": 0, "decimals": 0, "custom": {"drawStyle": "bars", "fillOpacity": 85, "lineWidth": 1, "stacking": {"mode": "normal"}}})
panels[-1]["fieldConfig"]["overrides"] = [
    {"matcher": {"id": "byName", "options": "aprobadas"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
    {"matcher": {"id": "byName", "options": "no aprobadas"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]}]
y += 8
add("table", "Sillas en disputa: solicitudes canceladas por silla", 0, y, 12, 8,
    [{"expr": "sort_desc(sum(taq_bloqueo_rechazo_asiento_total) by (asiento, motivo) - (sum(taq_bloqueo_rechazo_asiento_total offset $__range) by (asiento, motivo) or sum(taq_bloqueo_rechazo_asiento_total) by (asiento, motivo) * 0))", "instant": True, "format": "table"}],
    "short", "", None, None, {"cellHeight": "sm"})
panels[-1]["transformations"] = [{"id": "organize", "options": {"excludeByName": {"Time": True}, "renameByName": {"asiento": "Silla", "motivo": "Motivo", "Value": "Canceladas"}}}]
add("timeseries", "Bloqueos activos y liberados por vencimiento (8 min)", 12, y, 12, 8,
    [{"expr": "taq_bloqueos_activos", "legendFormat": "bloqueos activos"}, {"expr": "taq_bloqueo_liberados_total", "legendFormat": "liberados por vencimiento (acum.)"}])

dash = {"uid": "exp2asr", "title": "EXP-2 ASR: E-1 escalabilidad y D-3 con réplicas", "schemaVersion": 39, "version": 2,
        "refresh": "5s", "time": {"from": "now-25m", "to": "now"}, "panels": panels}
cm = {"apiVersion": "v1", "kind": "ConfigMap",
      "metadata": {"name": "taq-dash-exp2", "namespace": "monitoring", "labels": {"grafana_dashboard": "1"}},
      "data": {"exp2.json": json.dumps(dash, indent=1)}}
pathlib.Path(__file__).with_name("exp2-dashboard-local.yaml" if LOCAL else "exp2-dashboard.yaml").write_text(json.dumps(cm))
print("paneles:", len([p for p in panels if p["type"] != "row"]))
