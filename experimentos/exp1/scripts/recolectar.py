#!/usr/bin/env python3
"""Recolecta las métricas de una corrida de EXP-1 desde Prometheus y la bitácora del cliente.
Escribe metricas.json, metricas.md, graficas/*.png y prometheus/*.json en la carpeta de la corrida.

Uso: recolectar.py <carpeta_corrida> [url_prometheus]
"""
import csv, json, math, statistics, sys, time, urllib.parse, urllib.request
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

run = Path(sys.argv[1])
PROM = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:30900"
ej = json.loads((run / "ejecucion.json").read_text())
T0, T_CAL, T_FIN = ej["inicio_epoch_ms"] / 1000, ej["fin_calentamiento_epoch_ms"] / 1000, ej["fin_trafico_epoch_ms"] / 1000
VENTANA = int(T_FIN - T_CAL)  # 720 s de tráfico normal


def _servidor():
    with urllib.request.urlopen(f"{PROM}/api/v1/query?query=vector(time())", timeout=30) as r:
        return float(json.load(r)["data"]["result"][0]["value"][1])
_a = time.time(); _srv = _servidor(); _b = time.time()
OFF = _srv - (_a + _b) / 2     # reloj de Prometheus menos reloj de esta máquina (s)


def q(expr, t=None):
    p = {"query": expr}
    if t: p["time"] = f"{t + OFF:.3f}"
    with urllib.request.urlopen(f"{PROM}/api/v1/query?" + urllib.parse.urlencode(p), timeout=30) as r:
        return json.load(r)["data"]["result"]


def qr(expr, ini, fin, paso=5):
    p = {"query": expr, "start": f"{ini + OFF:.3f}", "end": f"{fin + OFF:.3f}", "step": paso}
    with urllib.request.urlopen(f"{PROM}/api/v1/query_range?" + urllib.parse.urlencode(p), timeout=60) as r:
        return json.load(r)["data"]["result"]


def cuantil(buckets, p):
    """buckets: [(le, acumulado)] como histogram_quantile de Prometheus (interpolación lineal)."""
    buckets = sorted(buckets, key=lambda x: x[0])
    total = buckets[-1][1]
    if total == 0: return None
    objetivo, prev_le, prev_c = p * total, 0.0, 0.0
    for le, c in buckets:
        if c >= objetivo:
            if math.isinf(le): return prev_le
            return prev_le + (le - prev_le) * ((objetivo - prev_c) / (c - prev_c) if c > prev_c else 0)
        prev_le, prev_c = le, c
    return None


def buckets_ventana(filtro):
    res = q(f'sum(increase(taq_reservar_seconds_bucket{{{filtro}}}[{VENTANA}s])) by (le)', T_FIN)
    return [(float("inf") if r["metric"]["le"] == "+Inf" else float(r["metric"]["le"]), float(r["value"][1])) for r in res]


def frac_le(buckets, limite):
    total = max(c for _, c in buckets)
    return None if not total else max(c for le, c in buckets if le <= limite + 1e-9) / total


out = {"semilla": ej["semilla"], "ventana_s": VENTANA, "desfase_reloj_prometheus_s": OFF}
# ---------- L-1 desde el gateway (Prometheus)
for nombre, filtro in [("ok", 'resultado="OK"'), ("todas", 'resultado=~".+"')]:
    b = buckets_ventana(filtro)
    out[f"gateway_{nombre}"] = {
        "n": max((c for _, c in b), default=0),
        "p50_ms": (cuantil(b, .5) or 0) * 1000, "p95_ms": (cuantil(b, .95) or 0) * 1000, "p99_ms": (cuantil(b, .99) or 0) * 1000,
        "fraccion_le_150ms": frac_le(b, 0.150) if b else None}
rech = q(f'sum(increase(taq_rechazos_cola_llena_total[{VENTANA}s]))', T_FIN)
out["rechazos_cola_llena"] = float(rech[0]["value"][1]) if rech else 0
out["reservar_por_resultado"] = {r["metric"].get("resultado"): float(r["value"][1]) for r in
    q(f'sum(increase(taq_reservar_seconds_count[{VENTANA}s])) by (resultado)', T_FIN)}

# ---------- Lado cliente (JMeter / bitácora)
def p(v, pc):
    v = sorted(v); k = (len(v) - 1) * pc; f, c = math.floor(k), math.ceil(k)
    return v[int(k)] if f == c else v[f] + (v[c] - v[f]) * (k - f)

lat_ok, lat_all, retrasos = [], [], []
with open(run / "bitacora.csv") as f:
    for r in csv.DictReader(f):
        ini = int(r["t_inicio_ms"]) / 1000
        retrasos.append(int(r["retraso_ms"]))
        if r["tipo"] == "CONFIRMAR": continue
        if not (T_CAL <= ini < T_FIN): continue
        ms = int(r["t_fin_ms"]) - int(r["t_inicio_ms"])
        lat_all.append(ms)
        if r["resultado"] == "OK": lat_ok.append(ms)
out["cliente_ok"] = {"n": len(lat_ok), "p50_ms": p(lat_ok, .5), "p95_ms": p(lat_ok, .95), "p99_ms": p(lat_ok, .99),
                     "fraccion_le_150ms": sum(1 for x in lat_ok if x <= 150) / len(lat_ok)}
out["cliente_todas"] = {"n": len(lat_all), "p50_ms": p(lat_all, .5), "p95_ms": p(lat_all, .95), "p99_ms": p(lat_all, .99),
                        "fraccion_le_150ms": sum(1 for x in lat_all if x <= 150) / len(lat_all)}
out["diferencia_p95_cliente_menos_gateway_ms"] = out["cliente_ok"]["p95_ms"] - out["gateway_ok"]["p95_ms"]
out["generador"] = {"retraso_prom_ms": statistics.mean(retrasos), "retraso_p95_ms": p(retrasos, .95),
                    "retraso_p99_ms": p(retrasos, .99), "retraso_max_ms": max(retrasos)}
dif_n = abs(out["gateway_todas"]["n"] - out["cliente_todas"]["n"]) / max(1, out["gateway_todas"]["n"])
out["diferencia_conteo_gateway_cliente"] = dif_n
# Una corrida es válida solo si el generador cumplió su calendario (p95 del atraso <= 100 ms)
# y el gateway y el cliente vieron prácticamente las mismas solicitudes (<= 2 % de diferencia).
out["ejecucion_valida"] = bool(out["generador"]["retraso_p95_ms"] <= 100 and dif_n <= 0.02)
out["tasa_real_reservar_por_min"] = out["gateway_todas"]["n"] / (VENTANA / 60)

# ---------- Rangos para tableros y gráficas
(run / "prometheus").mkdir(exist_ok=True); (run / "graficas").mkdir(exist_ok=True)
INI, FIN = T0 - 10, max(T_FIN + 60, T0 + 1) 
consultas = {
    "p95_ok": 'histogram_quantile(0.95, sum(rate(taq_reservar_seconds_bucket{resultado="OK"}[1m])) by (le))',
    "p95_todas": 'histogram_quantile(0.95, sum(rate(taq_reservar_seconds_bucket[1m])) by (le))',
    "reservas_por_s": 'sum(rate(taq_reservar_seconds_count[30s])) by (resultado)',
    "cpu": 'process_cpu_usage*100',
    "heap": 'sum(jvm_memory_used_bytes{area="heap"}) by (componente)',
    "cola_solicitud": 'taq_cola_solicitud_profundidad',
    "cola_operacion": 'taq_cola_operacion_profundidad',
    "cola_persistencia": 'taq_cola_persistencia_profundidad',
    "hilo_unico_pct": 'rate(taq_hilo_unico_ocupado_nanos_total[30s])/1e9*100',
    "ops_hilo_unico": 'sum(rate(taq_bloqueo_ops_total[30s]))',
    "bloqueos_activos": 'taq_bloqueos_activos',
    "cache": 'sum(rate(taq_cache_asiento_total[30s])) by (resultado)',
}
datos = {k: qr(e, INI, FIN) for k, e in consultas.items()}
for k, v in datos.items(): (run / "prometheus" / f"{k}.json").write_text(json.dumps(v))


def serie(res):  # -> {etiqueta: [(t, v)]}
    s = {}
    for r in res:
        et = r["metric"].get("componente") or r["metric"].get("resultado") or "valor"
        s[et] = [(float(t) - OFF, float(v)) for t, v in r["values"] if v not in ("NaN", "+Inf", "-Inf")]
    return s


def en_ventana(pts): return [v for t, v in pts if T_CAL <= t <= T_FIN]


res = {}
cpu, heap = serie(datos["cpu"]), serie(datos["heap"])
res["cpu_pct"] = {c: {"prom": statistics.mean(en_ventana(p_)), "max": max(en_ventana(p_))} for c, p_ in cpu.items() if en_ventana(p_)}
res["heap_mb"] = {c: {"prom": statistics.mean(en_ventana(p_)) / 2**20, "max": max(en_ventana(p_)) / 2**20} for c, p_ in heap.items() if en_ventana(p_)}
for k in ("cola_solicitud", "cola_operacion", "cola_persistencia", "hilo_unico_pct", "ops_hilo_unico", "bloqueos_activos"):
    pts = [x for s in serie(datos[k]).values() for x in s]
    v = en_ventana(pts)
    res[k] = {"prom": statistics.mean(v), "max": max(v)} if v else None
ch = {r["metric"]["resultado"]: float(r["value"][1]) for r in q(f'sum(increase(taq_cache_asiento_total[{VENTANA}s])) by (resultado)', T_FIN)}
res["cache"] = {"hit": ch.get("hit", 0), "miss": ch.get("miss", 0),
                "tasa_hit": ch.get("hit", 0) / max(1, ch.get("hit", 0) + ch.get("miss", 0))}
ops = {r["metric"]["op"]: float(r["value"][1]) for r in q(f'sum(increase(taq_bloqueo_ops_total[{VENTANA}s])) by (op)', T_FIN)}
res["ops_bd_bloqueo_ventana"] = ops
out["prometheus"] = res

# ---------- Gráficas
def grafica(nombre, titulo, series_, ylabel, linea=None, escala=1.0):
    fig, ax = plt.subplots(figsize=(9, 3.4))
    for et, pts in series_.items():
        ax.plot([(t - T0) / 60 for t, _ in pts], [v * escala for _, v in pts], label=et, linewidth=1.4)
    ax.axvspan((T_CAL - T0) / 60, (T_FIN - T0) / 60, color="#2e7d32", alpha=0.06, label="ventana medida")
    if linea: ax.axhline(linea[0], color="#c62828", linestyle="--", linewidth=1, label=linea[1])
    ax.set_title(titulo, fontsize=10); ax.set_xlabel("minutos desde el inicio"); ax.set_ylabel(ylabel)
    ax.grid(alpha=.3); ax.legend(fontsize=7, loc="upper right"); fig.tight_layout()
    fig.savefig(run / "graficas" / f"{nombre}.png", dpi=130); plt.close(fig)

s = serie(datos["p95_ok"]); s2 = serie(datos["p95_todas"])
grafica("p95-reservar", "L-1 — p95 de reservar en el gateway (ventana de 1 min)", {"p95 solo OK": s.get("valor", []), "p95 todas": s2.get("valor", [])}, "ms", (150, "ASR 150 ms"), 1000)
grafica("reservas-por-segundo", "Reservas por segundo según resultado", serie(datos["reservas_por_s"]), "solicitudes/s")
grafica("cpu", "CPU por componente", cpu, "% de CPU del proceso")
grafica("heap-mb", "Memoria heap por componente", heap, "MB", None, 1 / 2**20)
cs = {"cola_solicitud": serie(datos["cola_solicitud"]).get("valor", []), "cola_operacion": serie(datos["cola_operacion"]).get("valor", []),
      "cola_persistencia": serie(datos["cola_persistencia"]).get("valor", [])}
grafica("colas", "Profundidad de las colas", cs, "mensajes")
grafica("hilo-unico", "Ocupación del hilo único de bd_bloqueo", serie(datos["hilo_unico_pct"]), "% de tiempo ocupado")
grafica("bloqueos-activos", "Bloqueos activos en bd_bloqueo", serie(datos["bloqueos_activos"]), "asientos bloqueados")
(run / "metricas.json").write_text(json.dumps(out, indent=2))

# ---------- Markdown
g, c = out["gateway_ok"], out["cliente_ok"]
cumple = g["p95_ms"] <= 150
def f(x): return f"{x:,.1f}"
md = f"""# Métricas L-1 — {run.name}

**Corrida {'VÁLIDA ✅' if out['ejecucion_valida'] else 'INVÁLIDA ⚠️ (el generador de carga se atrasó o el cliente y el gateway no vieron lo mismo; no usar para concluir)'}** — atraso del generador frente al calendario: p95 = {out['generador']['retraso_p95_ms']:.0f} ms, máx. = {out['generador']['retraso_max_ms']:.0f} ms; diferencia de solicitudes gateway vs. cliente = {dif_n*100:.2f} %; desfase de reloj de Prometheus = {OFF:.2f} s.

**Veredicto L-1: {'CUMPLE ✅' if cumple else 'NO CUMPLE ❌'}** — p95 de reservar en el gateway = **{f(g['p95_ms'])} ms** (ASR ≤ 150 ms), ventana de {VENTANA} s de tráfico normal (se excluye el minuto de calentamiento).

## Latencia de reservar

| Medición | Frontera | n | p50 (ms) | p95 (ms) | p99 (ms) | % ≤ 150 ms |
|---|---|---|---|---|---|---|
| **ASR — solo reservas exitosas** | gateway (Prometheus) | {int(g['n'])} | {f(g['p50_ms'])} | **{f(g['p95_ms'])}** | {f(g['p99_ms'])} | {g['fraccion_le_150ms']*100:.2f} % |
| Todas las respuestas (éxito + rechazo) | gateway (Prometheus) | {int(out['gateway_todas']['n'])} | {f(out['gateway_todas']['p50_ms'])} | {f(out['gateway_todas']['p95_ms'])} | {f(out['gateway_todas']['p99_ms'])} | {out['gateway_todas']['fraccion_le_150ms']*100:.2f} % |
| Solo exitosas | cliente (JMeter/bitácora) | {c['n']} | {f(c['p50_ms'])} | {f(c['p95_ms'])} | {f(c['p99_ms'])} | {c['fraccion_le_150ms']*100:.2f} % |
| Todas | cliente (JMeter/bitácora) | {out['cliente_todas']['n']} | {f(out['cliente_todas']['p50_ms'])} | {f(out['cliente_todas']['p95_ms'])} | {f(out['cliente_todas']['p99_ms'])} | {out['cliente_todas']['fraccion_le_150ms']*100:.2f} % |

- Diferencia del p95 (cliente − gateway, solo exitosas): **{f(out['diferencia_p95_cliente_menos_gateway_ms'])} ms** (red local de kind + kube-proxy + cliente HTTP).
- El p95 del gateway se calcula con histogramas de Prometheus (cubetas en 100, 125, 150, 200 ms…), por lo que se interpola dentro de la cubeta; el porcentaje ≤ 150 ms es exacto porque 150 ms es un borde de cubeta.
- Tasa real medida en el gateway: {out['tasa_real_reservar_por_min']:.0f} solicitudes de reservar por minuto (400 llegadas normales por minuto + las solicitudes de los conflictos).
- Resultados en la ventana: {', '.join(f"{k} = {int(v)}" for k, v in sorted(out['reservar_por_resultado'].items()))}. Rechazos por cola llena: {int(out['rechazos_cola_llena'])}.

![p95](graficas/p95-reservar.png)

## Recursos y colas (ventana medida)

| Componente | CPU prom. (%) | CPU máx. (%) | Heap prom. (MB) | Heap máx. (MB) |
|---|---|---|---|---|
""" + "\n".join(f"| {k} | {f(res['cpu_pct'][k]['prom'])} | {f(res['cpu_pct'][k]['max'])} | {f(res['heap_mb'].get(k, {'prom': 0})['prom'])} | {f(res['heap_mb'].get(k, {'max': 0})['max'])} |" for k in sorted(res['cpu_pct'])) + f"""

| Indicador | Promedio | Máximo |
|---|---|---|
| Profundidad de `cola_solicitud` | {f(res['cola_solicitud']['prom'])} | {f(res['cola_solicitud']['max'])} |
| Profundidad de `cola_operacion` (hilo único) | {f(res['cola_operacion']['prom'])} | {f(res['cola_operacion']['max'])} |
| Profundidad de `cola_persistencia` | {f(res['cola_persistencia']['prom'])} | {f(res['cola_persistencia']['max'])} |
| Ocupación del hilo único de `bd_bloqueo` (%) | {f(res['hilo_unico_pct']['prom'])} | {f(res['hilo_unico_pct']['max'])} |
| Operaciones por segundo en `bd_bloqueo` | {f(res['ops_hilo_unico']['prom'])} | {f(res['ops_hilo_unico']['max'])} |
| Bloqueos activos | {f(res['bloqueos_activos']['prom'])} | {f(res['bloqueos_activos']['max'])} |

- Caché de asientos: {int(res['cache']['hit'])} aciertos y {int(res['cache']['miss'])} fallos (tasa de acierto {res['cache']['tasa_hit']*100:.1f} %).
- Operaciones en `bd_bloqueo` durante la ventana: {', '.join(f'{k} = {int(v)}' for k, v in res['ops_bd_bloqueo_ventana'].items())}.
- CPU: porcentaje del proceso JVM (`process_cpu_usage`), no de la máquina.

![colas](graficas/colas.png)
![hilo único](graficas/hilo-unico.png)
![cpu](graficas/cpu.png)
![memoria](graficas/heap-mb.png)
![reservas por segundo](graficas/reservas-por-segundo.png)
![bloqueos activos](graficas/bloqueos-activos.png)
"""
(run / "metricas.md").write_text(md)
print(md[:1800])
