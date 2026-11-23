#!/usr/bin/env python3
"""Tablero COMPACTO de EXP-3 (uid exp3asr). El protagonista es S-1; S-2 va al final.
  1) S-1 detectar:        p95 de detección ≤ 100 ms (% dentro del límite, cuentas marcadas, solicitudes antes de la marca)
  2) ¿Qué tipo de atacante es?  bot individual / granja de cuentas / acaparador de asientos (etiqueta declarada por el generador)
  3) Reporte de seguridad: resumen por tipo y últimas marcas, leídos de bd_auditoria (fuente de datos PostgreSQL 'pgseg')
  4) S-2 recuperarse:     p95 de recuperación ≤ 300 ms (% dentro del límite, asientos liberados, órdenes canceladas, cuentas revocadas)
El detalle de diagnóstico (etapas, colas, reglas) sigue en el tablero exp3asr-detalle.
Uso: python3 gen-dashboard-exp3.py   |   LOCAL=1 python3 gen-dashboard-exp3.py"""
import json, os, pathlib
LOCAL = bool(os.environ.get("LOCAL"))
DS = {"type": "prometheus", "uid": "prom"}
PG = {"type": "grafana-postgresql-datasource", "uid": "pgseg"}
panels = []
def add(tipo, titulo, x, y, w, h, targets, unit="short", desc="", thresholds=None, extra=None, opts=None, ds=None):
    d = ds or DS
    p = {"id": len(panels) + 1, "type": tipo, "title": titulo, "description": desc, "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "datasource": d, "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
         "targets": [dict(t, refId=chr(65 + i), datasource=d) for i, t in enumerate(targets)]}
    if thresholds:
        p["fieldConfig"]["defaults"]["thresholds"] = {"mode": "absolute", "steps": thresholds}
        p["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
    if extra: p["fieldConfig"]["defaults"].update(extra)
    if opts: p["options"] = opts
    panels.append(p)
def row(t, y): panels.append({"id": len(panels) + 1, "type": "row", "title": t, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "collapsed": False})
last = {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}
def sobre(v): return [{"color": "green", "value": None}, {"color": "red", "value": v}]
def linea(v, n): return {"expr": f"vector({v})", "legendFormat": n}
def q(m, p, w): return f'histogram_quantile({p}, sum(rate({m}_bucket[{w}])) by (le))'
DET, REC = "taq_deteccion_seconds", "taq_recuperacion_seconds"
curva = {"custom": {"lineInterpolation": "linear", "showPoints": "always", "spanNulls": True, "pointSize": 5}}
def percentiles(m, lim, nombre_lim, w="2m"):
    """Solo el p95 (la medida del ASR) y la línea del límite."""
    return [{"expr": q(m, 0.95, w), "legendFormat": "p95"}, linea(lim, nombre_lim)]
# Tipo de atacante = etiqueta `tipoAtacante` que declara el generador (métrica: label `tipo`; auditoría: columna `tipo_atacante`). No hay clasificador.
TIPOS = [("Bot individual", "bot_individual"), ("Granja de cuentas", "granja_cuentas"), ("Acaparador de asientos", "acaparador")]
SQL_TIPO = ("CASE tipo_atacante WHEN 'bot_individual' THEN 'Bot individual' WHEN 'granja_cuentas' THEN 'Granja de cuentas' "
            "WHEN 'acaparador' THEN 'Acaparador de asientos' ELSE 'Sin etiqueta' END")
def sql(txt): return {"rawSql": txt, "format": "table", "rawQuery": True, "editorMode": "code"}

y = 0
row("S-1  Detectar el ataque — medida: p95 ≤ 100 ms (desde que el evento sale de la cola de tráfico hasta que queda la evidencia en bd_auditoria)", y); y += 1
add("stat", "p95 de detección", 0, y, 3, 6, [{"expr": q(DET, 0.95, "5m"), "instant": True}], "s", "Verde = cumple S-1 (≤ 100 ms).", sobre(0.1), {"decimals": 4}, last)
add("stat", "% de detecciones ≤ 100 ms", 3, y, 3, 6,
    [{"expr": f'100 * sum(increase({DET}_bucket{{le="0.1"}}[5m])) / sum(increase({DET}_count[5m]))', "instant": True}], "percent",
    "Para que el p95 cumpla debe ser ≥ 95 %.", [{"color": "red", "value": None}, {"color": "green", "value": 95}], {"decimals": 1, "min": 0, "max": 100}, last)
add("stat", "Cuentas marcadas", 6, y, 3, 6, [{"expr": "sum(taq_cuentas_sospechosas_total) or vector(0)", "instant": True}], "short",
    "Cuentas de atacantes detectadas desde el inicio de la corrida.", [{"color": "blue", "value": None}], {"decimals": 0}, last)
add("stat", "Solicitudes que pasaron antes de la marca", 9, y, 3, 6,
    [{"expr": "sum(increase(taq_solicitudes_fraudulentas_antes_de_marca_sum[5m])) / sum(increase(taq_solicitudes_fraudulentas_antes_de_marca_count[5m]))", "instant": True}], "short",
    "Promedio por cuenta. La detección es asíncrona: el gateway no espera, así que las primeras solicitudes pasan.", [{"color": "blue", "value": None}], {"decimals": 1}, last)
add("timeseries", "Detección: p95 vs. límite del ASR (100 ms)", 12, y, 12, 6, percentiles(DET, 0.1, "límite ASR 100 ms"), "s", "", None, curva); y += 6

row("¿Qué tipo de atacante es? — el tipo es la etiqueta `tipoAtacante` de la solicitud (el detector no clasifica)", y); y += 1
add("timeseries", "Cuentas marcadas por minuto, por tipo de atacante", 0, y, 12, 6,
    [{"expr": f'sum(increase(taq_ataques_detectados_total{{tipo="{t}"}}[1m])) or vector(0)', "legendFormat": nombre} for nombre, t in TIPOS],
    "short",
    "Siempre se muestran los tres tipos (en 0 si aún no hubo ataques de ese tipo). El tipo es la etiqueta que declara el generador en cada solicitud del ataque; "
    "el detector solo la copia al registro, no clasifica.", None,
    {"min": 0, "decimals": 0, "custom": {"drawStyle": "bars", "fillOpacity": 80, "lineWidth": 1, "stacking": {"mode": "normal"}}})
panels[-1]["fieldConfig"]["overrides"] = [
    {"matcher": {"id": "byName", "options": n}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
    for n, c in [("Bot individual", "purple"), ("Granja de cuentas", "orange"), ("Acaparador de asientos", "yellow")]]
for i, (nombre, t) in enumerate(TIPOS):
    add("stat", nombre, 12 + i * 4, y, 4, 6, [{"expr": f'sum(taq_ataques_detectados_total{{tipo="{t}"}}) or vector(0)', "instant": True}], "short",
        "Cuentas marcadas de este tipo desde el inicio.", [{"color": ["purple", "orange", "yellow"][i], "value": None}], {"decimals": 0}, last)
y += 6

row("Reporte de seguridad — lo que registra bd_auditoria y lo que dispara S-2 (sigue el rango de tiempo del tablero)", y); y += 1
add("table", "Resumen por tipo de atacante", 0, y, 10, 9, [sql(
    f"SELECT {SQL_TIPO} AS \"Tipo de atacante\", count(*) AS \"Cuentas marcadas\", count(DISTINCT actor_ip) AS \"IP distintas\", "
    "round(avg((detalle->>'solicitudes_en_ventana')::numeric), 1) AS \"Solicitudes antes de la marca\", "
    "round(percentile_cont(0.95) WITHIN GROUP (ORDER BY (ts_evidencia - ts_evento_detector))::numeric, 1) AS \"p95 detección (ms)\", "
    "string_agg(DISTINCT detalle->>'regla', ', ') AS \"Regla que disparó\", to_char(min(ts), 'HH24:MI:SS') AS \"Primera\", to_char(max(ts), 'HH24:MI:SS') AS \"Última\" "
    "FROM auditoria_seguridad WHERE tipo = 'ATAQUE_DETECTADO' AND $__timeFilter(ts) GROUP BY 1 ORDER BY 2 DESC")],
    "short", "Una fila por tipo. La detección en ms tiene resolución de 1 ms; el p95 fino está en la gráfica de arriba.", None, None, {"cellHeight": "sm"}, ds=PG)
add("table", "Últimas marcas (evidencia: cuenta, IP, hora)", 10, y, 14, 9, [sql(
    f"SELECT to_char(ts, 'HH24:MI:SS.MS') AS \"Hora\", {SQL_TIPO} AS \"Tipo\", actor_cuenta AS \"Cuenta\", actor_ip AS \"IP\", "
    "detalle->>'regla' AS \"Regla\", (detalle->>'solicitudes_en_ventana')::int AS \"Solicitudes en la ventana\", "
    "(ts_evidencia - ts_evento_detector) AS \"Detección (ms)\" "
    "FROM auditoria_seguridad WHERE tipo = 'ATAQUE_DETECTADO' AND $__timeFilter(ts) ORDER BY id DESC LIMIT 12")],
    "short", "Las 12 marcas más recientes.", None, None, {"cellHeight": "sm"}, ds=PG); y += 9

row("S-2  Recuperarse del ataque — medida: p95 ≤ 300 ms (desde la alerta hasta asientos liberados + órdenes canceladas + cuentas revocadas)", y); y += 1
add("stat", "p95 de recuperación", 0, y, 3, 6, [{"expr": q(REC, 0.95, "5m"), "instant": True}], "s", "Verde = cumple S-2 (≤ 300 ms).", sobre(0.3), {"decimals": 4}, last)
add("stat", "% de recuperaciones ≤ 300 ms", 3, y, 3, 6,
    [{"expr": f'100 * sum(increase({REC}_bucket{{le="0.3"}}[5m])) / sum(increase({REC}_count[5m]))', "instant": True}], "percent",
    "Para que el p95 cumpla debe ser ≥ 95 %.", [{"color": "red", "value": None}, {"color": "green", "value": 95}], {"decimals": 1, "min": 0, "max": 100}, last)
add("stat", "Asientos liberados", 6, y, 3, 6, [{"expr": "sum(taq_bloqueo_liberados_ataque_total) or vector(0)", "instant": True}], "short", "", [{"color": "blue", "value": None}], {"decimals": 0}, last)
add("stat", "Órdenes canceladas", 9, y, 3, 6, [{"expr": "sum(taq_ordenes_canceladas_total) or vector(0)", "instant": True}], "short", "", [{"color": "blue", "value": None}], {"decimals": 0}, last)
add("stat", "Cuentas revocadas", 12, y, 3, 6, [{"expr": "sum(taq_cuentas_revocadas_total) or vector(0)", "instant": True}], "short", "", [{"color": "blue", "value": None}], {"decimals": 0}, last)
add("timeseries", "Recuperación: p95 vs. límite del ASR (300 ms)", 15, y, 9, 6, percentiles(REC, 0.3, "límite ASR 300 ms"), "s", "", None, curva)

dash = {"uid": "exp3asr", "title": "EXP-3 ASR: S-1 detectar (tipos de atacante) y S-2 recuperarse", "schemaVersion": 39, "version": 6,
        "refresh": "10s", "time": {"from": "now-15m", "to": "now"}, "panels": panels}
cm = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "taq-dash-exp3", "namespace": "monitoring", "labels": {"grafana_dashboard": "1"}},
      "data": {"exp3.json": json.dumps(dash, indent=1)}}
pathlib.Path(__file__).with_name("exp3-dashboard-local.yaml" if LOCAL else "exp3-dashboard.yaml").write_text(json.dumps(cm))
print("paneles:", len([p for p in panels if p["type"] != "row"]))
