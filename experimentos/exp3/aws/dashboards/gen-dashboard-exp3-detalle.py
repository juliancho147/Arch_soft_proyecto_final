#!/usr/bin/env python3
"""Genera el tablero de EXP-3 (S-1 detectar y S-2 recuperarse) como ConfigMap para el Grafana de kube-prometheus-stack
(namespace monitoring, etiqueta grafana_dashboard: "1"; uid exp3asr). Solo paneles que muestran el cumplimiento de los ASR:
verde = dentro del límite, rojo = fuera. Nada de CPU ni memoria.

Uso: python3 gen-dashboard-exp3.py            (EKS: exp3-dashboard.yaml)
     LOCAL=1 python3 gen-dashboard-exp3.py    (kind: exp3-dashboard-local.yaml; mismo contenido, no depende de métricas de Kubernetes)
     BOTS_ESPERADOS=4000 ...                  (bots que inyecta la corrida: 40 ataques x 100; solo para la línea de referencia)"""
import json, os, pathlib
LOCAL = bool(os.environ.get("LOCAL"))
BOTS = int(os.environ.get("BOTS_ESPERADOS", "4000"))
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
LIM_S1, LIM_S2, LIM_E1 = 0.1, 0.3, 0.25         # ASR S-1 (100 ms), S-2 (300 ms) y E-1 (250 ms, tráfico de los demás compradores)
def sobreumbral(v): return [{"color": "green", "value": None}, {"color": "red", "value": v}]
def linea(v, nombre): return {"expr": f"vector({v})", "legendFormat": nombre}
Q = 'histogram_quantile(0.95, sum(rate({m}_bucket[{w}])) by (le))'
# Con pocos eventos por segundo (un ataque dura segundos) conviene una ventana larga para el p95.
DET, REC = "taq_deteccion_seconds", "taq_recuperacion_seconds"
curva = {"custom": {"lineInterpolation": "linear", "showPoints": "always", "spanNulls": True, "pointSize": 5}}
y = 0
row(f"S-1  Detectar el ataque: p95 ≤ {int(LIM_S1*1000)} ms desde que el evento entra al detector hasta que queda la evidencia en bd_auditoria", y); y += 1
add("stat", "p95 de detección (últimos 5 min)", 0, y, 4, 6, [{"expr": Q.format(m=DET, w="5m"), "instant": True}], "s",
    "Verde = cumple S-1 (≤ 100 ms). Incluye el INSERT en bd_auditoria.", sobreumbral(LIM_S1), {"decimals": 4}, last)
add("stat", "% de detecciones ≤ 100 ms (5 min)", 4, y, 4, 6,
    [{"expr": f'100 * sum(increase({DET}_bucket{{le="0.1"}}[5m])) / sum(increase({DET}_count[5m]))', "instant": True}], "percent",
    "Debe ser ≥ 95 % para que el p95 cumpla.", [{"color": "red", "value": None}, {"color": "green", "value": 95}], {"decimals": 1, "max": 100, "min": 0}, last)
add("stat", "Compradores legítimos marcados", 8, y, 4, 6,
    [{"expr": "sum(taq_marcas_falsos_positivos_total) or vector(0)", "instant": True}], "short",
    "Marcas sobre cuentas que no son bots. Lo esperado es 0.", [{"color": "green", "value": None}, {"color": "red", "value": 1}], {"decimals": 0}, last)
add("timeseries", "p95 de detección vs. límite del ASR (100 ms)", 12, y, 12, 6,
    [{"expr": Q.format(m=DET, w="2m"), "legendFormat": "p95 detección"}, linea(LIM_S1, "límite ASR 100 ms")], "s", "", None, curva); y += 6
add("timeseries", "Cuentas de bots marcadas (acumulado) vs. bots inyectados", 0, y, 12, 7,
    [{"expr": "sum(taq_cuentas_sospechosas_total)", "legendFormat": "cuentas marcadas"}, linea(BOTS, f"bots inyectados en la corrida ({BOTS})")], "short",
    "Se espera que la curva llegue a la línea: todos los ataques detectados.", None, {"min": 0, "decimals": 0})
add("timeseries", "Cola de eventos de tráfico (¿el detector se atrasa en el pico?)", 12, y, 12, 7,
    [{"expr": "max(taq_cola_evento_trafico_profundidad)", "legendFormat": "eventos en cola_evento_trafico"},
     {"expr": "sum(rate(taq_eventos_trafico_descartados_total[30s])) or vector(0)", "legendFormat": "eventos descartados/s"}], "short",
    "El detector es asíncrono: la cola puede crecer sin frenar al comprador, pero si se llena se descartan eventos.", None, {"min": 0}); y += 7
add("timeseries", "Solicitudes fraudulentas que pasaron antes de la marca (promedio por bot)", 0, y, 12, 6,
    [{"expr": "sum(increase(taq_solicitudes_fraudulentas_antes_de_marca_sum[2m])) / sum(increase(taq_solicitudes_fraudulentas_antes_de_marca_count[2m]))", "legendFormat": "solicitudes por bot antes de la marca"}],
    "short", "La detección es asíncrona: las primeras solicitudes de un bot pasan antes de la marca (con el umbral por defecto, 3).", None, curva)
add("timeseries", "Ataques detectados por regla (por minuto)", 12, y, 12, 6,
    [{"expr": "sum(increase(taq_ataques_detectados_total[1m])) by (regla)", "legendFormat": "{{regla}}"}], "short", "", None,
    {"min": 0, "decimals": 0, "custom": {"drawStyle": "bars", "fillOpacity": 70, "lineWidth": 1}}); y += 6

row(f"S-2  Recuperarse del ataque: p95 ≤ {int(LIM_S2*1000)} ms desde la alerta hasta asientos liberados + órdenes canceladas + cuentas revocadas", y); y += 1
add("stat", "p95 de recuperación (últimos 5 min)", 0, y, 4, 6, [{"expr": Q.format(m=REC, w="5m"), "instant": True}], "s",
    "Verde = cumple S-2 (≤ 300 ms). Medido por componente_respuesta_ataque; la medida independiente sale de medir_recuperacion.py.", sobreumbral(LIM_S2), {"decimals": 4}, last)
add("stat", "% de recuperaciones ≤ 300 ms (5 min)", 4, y, 4, 6,
    [{"expr": f'100 * sum(increase({REC}_bucket{{le="0.3"}}[5m])) / sum(increase({REC}_count[5m]))', "instant": True}], "percent",
    "Debe ser ≥ 95 % para que el p95 cumpla.", [{"color": "red", "value": None}, {"color": "green", "value": 95}], {"decimals": 1, "max": 100, "min": 0}, last)
add("stat", "Asientos liberados por ataque (acumulado)", 8, y, 4, 6, [{"expr": "sum(taq_bloqueo_liberados_ataque_total) or vector(0)", "instant": True}], "short",
    "Asientos de bots devueltos al inventario por el índice en memoria de bd_bloqueo.", [{"color": "blue", "value": None}], {"decimals": 0}, last)
add("timeseries", "p95 de recuperación vs. límite del ASR (300 ms)", 12, y, 12, 6,
    [{"expr": Q.format(m=REC, w="2m"), "legendFormat": "p95 recuperación"}, linea(LIM_S2, "límite ASR 300 ms")], "s", "", None, curva); y += 6
add("timeseries", "Etapas de la recuperación (p95): ¿cuál se acerca al límite?", 0, y, 12, 7,
    [{"expr": 'histogram_quantile(0.95, sum(rate(taq_recuperacion_etapa_seconds_bucket[2m])) by (le, etapa))', "legendFormat": "{{etapa}}"}, linea(LIM_S2, "límite ASR 300 ms")],
    "s", "Espera de la alerta, revocación en Redis, liberación en bd_bloqueo (cola del hilo único) y cancelación de órdenes en Postgres.", None, curva)
add("timeseries", "Cola de operaciones de bd_bloqueo durante la liberación masiva", 12, y, 12, 7,
    [{"expr": "max_over_time(taq_cola_operacion_profundidad[5s])", "legendFormat": "operaciones en cola (máx.)"},
     {"expr": 'histogram_quantile(0.95, sum(rate(taq_liberacion_ataque_seconds_bucket[2m])) by (le))', "legendFormat": "p95 liberar comprador (s, con espera en cola)"}], "short",
    "La liberación masiva entra por la cola del hilo único: si la cola crece, la espera sube y compromete los 300 ms.", None, {"min": 0}); y += 7

row("Sin afectar a los demás compradores (E-1: p95 < 250 ms)", y); y += 1
add("stat", "p95 de reservar (último minuto)", 0, y, 4, 6,
    [{"expr": 'histogram_quantile(0.95, sum(rate(taq_reservar_seconds_bucket[1m])) by (le))', "instant": True}], "s",
    "Todas las reservas del gateway (los bots son ~12 % del tráfico). Verde = por debajo de 250 ms. El p95 exacto del tráfico legítimo sale de la bitácora en verificar_exp3.py.",
    sobreumbral(LIM_E1), {"decimals": 3}, last)
add("timeseries", "p95 de reservar durante los ataques vs. límite (250 ms)", 4, y, 12, 6,
    [{"expr": 'histogram_quantile(0.95, sum(rate(taq_reservar_seconds_bucket[30s])) by (le))', "legendFormat": "p95 reservar"}, linea(LIM_E1, "límite 250 ms")], "s", "", None, curva)
add("timeseries", "Solicitudes por segundo del gateway y rechazos por cuenta revocada", 16, y, 8, 6,
    [{"expr": "sum(rate(taq_reservar_seconds_count[30s]))", "legendFormat": "reservas/s"},
     {"expr": "sum(rate(taq_rechazos_cuenta_revocada_total[30s])) or vector(0)", "legendFormat": "403 cuenta revocada/s"}], "reqps"); y += 6

dash = {"uid": "exp3asr-detalle", "title": "EXP-3 detalle (diagnóstico): S-1 y S-2", "schemaVersion": 39, "version": 1,
        "refresh": "5s", "time": {"from": "now-30m", "to": "now"}, "panels": panels}
cm = {"apiVersion": "v1", "kind": "ConfigMap",
      "metadata": {"name": "taq-dash-exp3-detalle", "namespace": "monitoring", "labels": {"grafana_dashboard": "1"}},
      "data": {"exp3-detalle.json": json.dumps(dash, indent=1)}}
pathlib.Path(__file__).with_name("exp3-detalle-local.yaml" if LOCAL else "exp3-detalle.yaml").write_text(json.dumps(cm))
print("paneles:", len([p for p in panels if p["type"] != "row"]))
