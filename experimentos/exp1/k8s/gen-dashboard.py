#!/usr/bin/env python3
"""Genera 30-grafana-dashboard.json (ConfigMap) con solo los paneles que muestran los ASR y los conflictos."""
import json, pathlib
DS = {"type": "prometheus", "uid": "prom"}
panels = []
def add(tipo, titulo, x, y, w, h, targets, unit="short", desc="", thresholds=None, extra=None, opts=None):
    p = {"id": len(panels) + 1, "type": tipo, "title": titulo, "description": desc,
         "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": DS,
         "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
         "targets": [dict(t, refId=chr(65 + i), datasource=DS) for i, t in enumerate(targets)]}
    if thresholds:
        p["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": thresholds}
        p["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
    if extra: p["fieldConfig"]["defaults"].update(extra)
    if opts: p["options"] = opts
    panels.append(p)
def row(titulo, y):
    panels.append({"id": len(panels) + 1, "type": "row", "title": titulo, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "collapsed": False})
VG = [{"color": "green", "value": None}, {"color": "red", "value": 0.15}]
last = {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}

row("L-1  Latencia de reservar: p95 ≤ 150 ms", 0)
add("stat", "p95 (ventana 5 min)", 0, 1, 5, 6,
    [{"expr": 'histogram_quantile(0.95, sum(rate(taq_reservar_seconds_bucket[5m])) by (le))', "instant": True}],
    "s", "Verde = cumple el ASR (≤150 ms). Rojo = lo incumple.", VG, {"decimals": 3}, last)
add("stat", "Solicitudes recibidas en el rango", 5, 1, 5, 6,
    [{"expr": 'sum(taq_reservar_seconds_count) - (sum(taq_reservar_seconds_count offset $__range) or vector(0))', "instant": True}],
    "short", "Solicitudes de reserva que entraron al gateway dentro del rango de tiempo del tablero (con la vista reiniciada, desde el reinicio).",
    [{"color": "blue", "value": None}], {"decimals": 0}, last)
add("timeseries", "p95 en el tiempo vs. límite del ASR", 10, 1, 14, 6,
    [{"expr": 'histogram_quantile(0.95, sum(rate(taq_reservar_seconds_bucket[30s])) by (le))', "legendFormat": "p95 reservar"},
     {"expr": "vector(0.15)", "legendFormat": "límite ASR 150 ms"}], "s")

row("D-3  Una silla, una sola reserva: cuando llegan varias solicitudes a la misma silla solo una se aprueba", 7)
add("timeseries", "Solicitudes simultáneas a una misma silla en el tiempo", 0, 8, 15, 9,
    [{"expr": "taq_conflicto_pico_misma_silla", "legendFormat": "solicitudes a la misma silla"}],
    "short", "Plano en 0 mientras no hay disputa. Cada pico es una ráfaga: varios compradores pidiendo la misma silla a la vez "
             "(se mantiene ~12 s para que se alcance a ver).",
    None, {"min": 0, "decimals": 0, "color": {"mode": "fixed", "fixedColor": "purple"},
           "custom": {"drawStyle": "line", "lineInterpolation": "stepAfter", "fillOpacity": 30, "lineWidth": 2, "showPoints": "never"}})
add("timeseries", "Solicitudes en conflicto por tiempo: aprobadas vs. no aprobadas", 15, 8, 9, 9,
    [{"expr": 'taq_rafaga_aprobadas', "legendFormat": "aprobadas"},
     {"expr": 'taq_rafaga_canceladas', "legendFormat": "no aprobadas"}],
    "short", "Valores exactos de la última ráfaga (se mantienen ~12 s): 1 verde (aprobada) + el resto rojo (no aprobadas) = total de solicitudes de la ráfaga.",
    None, {"min": 0, "decimals": 0, "custom": {"drawStyle": "bars", "fillOpacity": 85, "lineWidth": 1, "stacking": {"mode": "normal"}, "barAlignment": 0}})
panels[-1]["fieldConfig"]["overrides"] = [
    {"matcher": {"id": "byName", "options": "aprobadas"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "green"}}]},
    {"matcher": {"id": "byName", "options": "no aprobadas"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]}]
add("table", "Sillas en disputa: cuántas solicitudes se cancelaron por cada silla", 0, 17, 24, 8,
    [{"expr": 'sort_desc(sum(taq_bloqueo_rechazo_asiento_total) by (asiento, motivo) - (sum(taq_bloqueo_rechazo_asiento_total offset $__range) by (asiento, motivo) or sum(taq_bloqueo_rechazo_asiento_total) by (asiento, motivo) * 0))', "instant": True, "format": "table"}],
    "short", "Cada fila es una silla con conflicto; 'Cancelada' = solicitudes rechazadas (la ganadora no aparece: fue confirmada).",
    None, None, {"cellHeight": "sm", "sortBy": [{"displayName": "Canceladas", "desc": True}]})
panels[-1]["transformations"] = [{"id": "organize", "options": {"excludeByName": {"Time": True},
    "renameByName": {"asiento": "Silla", "motivo": "Motivo", "Value": "Canceladas"}}}]

row("D-3  Vencimiento del bloqueo a los 8 min", 25)
add("timeseries", "Bloqueos activos y liberados por vencimiento", 0, 26, 24, 7,
    [{"expr": "taq_bloqueos_activos", "legendFormat": "bloqueos activos"},
     {"expr": "taq_bloqueo_liberados_total", "legendFormat": "liberados por vencimiento (acum.)"}])
dash = {"uid": "exp1asr", "title": "EXP-1 ASR: L-1 latencia y D-3 doble reserva", "schemaVersion": 39, "version": 8,
        "refresh": "5s", "time": {"from": "now-20m", "to": "now"}, "panels": panels}
cm = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "grafana-dash", "namespace": "taq"},
      "data": {"exp1.json": json.dumps(dash, indent=1)}}
pathlib.Path(__file__).with_name("30-grafana-dashboard.json").write_text(json.dumps(cm))
