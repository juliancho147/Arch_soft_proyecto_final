#!/usr/bin/env python3
"""Recolecta de Prometheus (por el túnel localhost:30900) las métricas de una ejecución de EXP-2 y escribe metricas.md/json.
Uso: recolectar_exp2.py <carpeta> <pico_s> <calent_s> <rampa_s>"""
import csv, json, pathlib, statistics, sys, urllib.parse, urllib.request
carp = pathlib.Path(sys.argv[1]); pico_s, cal_s, ramp_s = (int(x) for x in sys.argv[2:5])
PROM = sys.argv[5] if len(sys.argv) > 5 else "http://localhost:30900"
ej = json.loads((carp / "ejecucion.json").read_text())
t0 = ej["inicio_epoch_ms"] / 1000
t_pico0, t_pico1 = t0 + cal_s + ramp_s, t0 + cal_s + ramp_s + pico_s
import time
def _servidor():
    with urllib.request.urlopen(f"{PROM}/api/v1/query?query=vector(time())", timeout=30) as r:
        return float(json.load(r)["data"]["result"][0]["value"][1])
_a = time.time(); _srv = _servidor(); _b = time.time()
OFF = _srv - (_a + _b) / 2          # reloj de Prometheus menos reloj de esta máquina (s); ≈0 en AWS, no en la VM de Docker local
def q(expr, t=None):
    u = PROM + "/api/v1/query?" + urllib.parse.urlencode({"query": expr, **({"time": f"{t + OFF:.3f}"} if t else {})})
    r = json.load(urllib.request.urlopen(u, timeout=30))["data"]["result"]
    return [(x["metric"], float(x["value"][1])) for x in r]
def rango(expr, a, b, paso=5):
    u = PROM + "/api/v1/query_range?" + urllib.parse.urlencode({"query": expr, "start": f"{a + OFF:.3f}", "end": f"{b + OFF:.3f}", "step": paso})
    res = json.load(urllib.request.urlopen(u, timeout=60))["data"]["result"]
    for s_ in res: s_["values"] = [[float(t) - OFF, v] for t, v in s_["values"]]      # de vuelta al reloj de esta máquina
    return res
def p95(a, b):
    r = q(f"histogram_quantile(0.95, sum(increase(taq_reservar_seconds_bucket[{int(b-a)}s])) by (le))", b)
    return r[0][1] * 1000 if r and r[0][1] == r[0][1] else None
def frac_bajo(a, b, lim):
    s = int(b - a); num = q(f'sum(increase(taq_reservar_seconds_bucket{{le="{lim}"}}[{s}s]))', b); den = q(f"sum(increase(taq_reservar_seconds_count[{s}s]))", b)
    return 100 * num[0][1] / den[0][1] if num and den and den[0][1] else None
M = {"ventanas": {"pico_inicio": t_pico0, "pico_fin": t_pico1}, "desfase_reloj_prometheus_s": round(OFF, 2)}
# Réplicas por deployment en el tiempo y momento de equilibrio (último cambio de réplicas)
rep = {}
for s in rango('kube_deployment_status_replicas_available{namespace="taq",deployment=~"nodo-.*"}', t0, t_pico1 + 60):
    rep[s["metric"]["deployment"]] = [(float(t), int(float(v))) for t, v in s["values"]]
M["replicas"] = {}
t_eq = t0
for dep, serie in rep.items():
    cambios = [t for (t, v), (_, v0) in zip(serie[1:], serie[:-1]) if v != v0]
    ultimo = cambios[-1] if cambios else t0
    M["replicas"][dep] = {"maximo": max(v for _, v in serie), "final": serie[-1][1], "ultimo_cambio_s": round(ultimo - t0)}
    t_eq = max(t_eq, ultimo)
M["equilibrio_desde_s"] = round(t_eq - t0)
# E-1: p95 en el pico completo (incluye arranque de réplicas) y solo después del equilibrio
M["p95_pico_completo_ms"] = p95(t_pico0, t_pico1)
M["p95_tras_equilibrio_ms"] = p95(max(t_eq, t_pico0), t_pico1) if t_eq < t_pico1 - 30 else None
# 250 ms no es borde de cubeta del histograma: además del p95 se reporta el % bajo 200 ms y bajo 300 ms
M["pct_bajo_200ms_pico"] = frac_bajo(t_pico0, t_pico1, "0.2"); M["pct_bajo_300ms_pico"] = frac_bajo(t_pico0, t_pico1, "0.3")
tot = q(f"sum(increase(taq_reservar_seconds_count[{int(t_pico1-t_pico0)}s]))", t_pico1)
M["solicitudes_en_pico"] = tot[0][1] if tot else None
M["solicitudes_por_min_en_pico"] = tot[0][1] / (pico_s / 60) if tot else None
rech = q("sum(taq_rechazos_cola_llena_total)", t_pico1 + 30); M["rechazos_cola_llena_total"] = rech[0][1] if rech else 0
err = q(f'sum(increase(taq_reservar_seconds_count{{resultado!~"OK|NO_DISPONIBLE"}}[{int(t_pico1-t0)}s]))', t_pico1)
M["errores_tecnicos"] = err[0][1] if err else 0
# Hilo único
ops = rango("sum(rate(taq_bloqueo_ops_total[30s]))", t_pico0, t_pico1); oc = rango("rate(taq_hilo_unico_ocupado_nanos_total[30s])/1e9*100", t_pico0, t_pico1)
cola = rango("max_over_time(taq_cola_operacion_profundidad[15s])", t_pico0, t_pico1)
vals = lambda r: [float(v) for s in r for _, v in s["values"]]
M["hilo_unico"] = {"ops_s_max": max(vals(ops) or [0]), "ops_s_prom": statistics.mean(vals(ops) or [0]),
                   "ocupado_pct_max": max(vals(oc) or [0]), "cola_operacion_max": max(vals(cola) or [0])}
# Lado del cliente (bitácora de JMeter): p95 en la ventana del pico y retraso del generador
lat = []; retr = []
with open(carp / "bitacora.csv") as f:
    for r in csv.DictReader(f):
        ini = int(r["t_inicio_ms"]) / 1000
        if r["tipo"] in ("NORMAL", "CONF_MISMO_ASIENTO", "CONF_GRUPOS_CRUZADOS", "CONF_VENDIDO", "CONF_MISMO_ASIENTO_SIN_VENDIDOS") and t_pico0 <= ini <= t_pico1:
            lat.append(int(r["t_fin_ms"]) - int(r["t_inicio_ms"]))
        retr.append(int(r["retraso_ms"]))
lat.sort(); retr.sort()
M["cliente"] = {"p95_pico_ms": lat[int(.95 * (len(lat) - 1))] if lat else None, "solicitudes_pico": len(lat),
                "retraso_generador_p95_ms": retr[int(.95 * (len(retr) - 1))] if retr else None}
M["valida"] = bool(M["cliente"]["retraso_generador_p95_ms"] is not None and M["cliente"]["retraso_generador_p95_ms"] <= 100)
M["asr_e1_cumple"] = (M["p95_pico_completo_ms"] is not None and M["p95_pico_completo_ms"] < 250 and M["rechazos_cola_llena_total"] == 0)

# Fases opcionales (variable FASES="nombre:ini_s:fin_s,..."): p95, tasa y réplicas máximas por fase. Si existe "pico8k", E-1 se evalúa sobre esa fase.
import os
if os.environ.get("FASES"):
    M["fases"] = {}
    for tramo in os.environ["FASES"].split(","):
        nombre, ini, fin = tramo.split(":"); a, b = t0 + float(ini), t0 + float(fin)
        tot_f = q(f"sum(increase(taq_reservar_seconds_count[{int(b-a)}s]))", b)
        err_f = q(f'sum(increase(taq_reservar_seconds_count{{resultado!~"OK|NO_DISPONIBLE"}}[{int(b-a)}s]))', b)
        M["fases"][nombre] = {"desde_s": float(ini), "hasta_s": float(fin), "p95_ms": p95(a, b),
            "pct_bajo_200ms": frac_bajo(a, b, "0.2"), "pct_bajo_300ms": frac_bajo(a, b, "0.3"),
            "solicitudes_por_min": (tot_f[0][1] / ((b - a) / 60)) if tot_f else None, "errores_tecnicos": err_f[0][1] if err_f else 0,
            "replicas_max": {d: max([v for t, v in sr if a <= t <= b] or [0]) for d, sr in rep.items()}}
    if "pico8k" in M["fases"]:
        f8 = M["fases"]["pico8k"]
        M["asr_e1_cumple"] = bool(f8["p95_ms"] is not None and f8["p95_ms"] < 250 and f8["errores_tecnicos"] == 0 and M["rechazos_cola_llena_total"] == 0)
(carp / "metricas.json").write_text(json.dumps(M, indent=2))
(carp / "prometheus").mkdir(exist_ok=True)
for nombre, expr in {"p95": "histogram_quantile(0.95, sum(rate(taq_reservar_seconds_bucket[30s])) by (le))",
                     "solicitudes_s": "sum(rate(taq_reservar_seconds_count[30s]))", "replicas": 'kube_deployment_status_replicas_available{namespace="taq"}',
                     "cpu_pods": 'sum(rate(container_cpu_usage_seconds_total{namespace="taq",container!=""}[30s])) by (container)',
                     "nodos": 'count(kube_node_status_condition{condition="Ready",status="true"})'}.items():
    (carp / "prometheus" / f"{nombre}.json").write_text(json.dumps(rango(expr, t0 - 30, t_pico1 + 120)))
f1 = lambda v: "n/d" if v is None else f"{v:.1f}"
L = [f"# EXP-2 — métricas de la ejecución", "",
     f"**E-1 (p95 < 250 ms durante el pico, sin perder solicitudes): {'✅ cumple' if M['asr_e1_cumple'] else '❌ no cumple'}**", "",
     f"| Medida | Valor |", "|---|---|",
     f"| p95 en los {pico_s//60} min del pico (con arranque de réplicas) | {f1(M['p95_pico_completo_ms'])} ms |",
     f"| p95 después del equilibrio | {f1(M['p95_tras_equilibrio_ms'])} ms |",
     f"| % de reservas ≤ 200 ms / ≤ 300 ms en el pico | {f1(M['pct_bajo_200ms_pico'])} % / {f1(M['pct_bajo_300ms_pico'])} % |",
     f"| p95 que ve el generador de carga | {M['cliente']['p95_pico_ms']} ms |",
     f"| Solicitudes en el pico | {f1(M['solicitudes_en_pico'])} (≈ {f1(M['solicitudes_por_min_en_pico'])}/min) |",
     f"| Rechazos por cola llena | {M['rechazos_cola_llena_total']} |", f"| Errores técnicos | {M['errores_tecnicos']} |",
     f"| Equilibrio de réplicas desde | {M['equilibrio_desde_s']} s del inicio |",
     f"| Hilo único: ops/s máx / prom · ocupado máx · cola máx | {f1(M['hilo_unico']['ops_s_max'])} / {f1(M['hilo_unico']['ops_s_prom'])} · {f1(M['hilo_unico']['ocupado_pct_max'])} % · {M['hilo_unico']['cola_operacion_max']} |",
     f"| Atraso del generador (p95) | {M['cliente']['retraso_generador_p95_ms']} ms → ejecución {'válida' if M['valida'] else 'NO válida'} |", "",
     "## Réplicas por pod", "", "| Pod | Máximo | Final | Último cambio |", "|---|---|---|---|"]
for d, v in sorted(M["replicas"].items()): L.append(f"| {d} | {v['maximo']} | {v['final']} | {v['ultimo_cambio_s']} s |")
if M.get("fases"):
    L += ["", "## Por fase", "", "| Fase | Solicitudes/min | p95 | ≤200 ms | ≤300 ms | Errores | Réplicas máx. |", "|---|---|---|---|---|---|---|"]
    for n_, f_ in M["fases"].items():
        L.append(f"| {n_} ({f_['desde_s']:.0f}–{f_['hasta_s']:.0f} s) | {f1(f_['solicitudes_por_min'])} | {f1(f_['p95_ms'])} ms | {f1(f_['pct_bajo_200ms'])} % | {f1(f_['pct_bajo_300ms'])} % | {f_['errores_tecnicos']:.0f} | " + ", ".join(f"{d.replace('nodo-','')} {v}" for d, v in sorted(f_['replicas_max'].items())) + " |")
(carp / "metricas.md").write_text("\n".join(L) + "\n")
print("métricas escritas en", carp)
