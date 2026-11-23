#!/usr/bin/env python3
"""EXP-3: cruza la bitácora del generador con bd_auditoria, el estado final (bd_bloqueo, Redis, Postgres) y Prometheus.
Escribe verificacion.json y verificacion.md en la carpeta de la corrida.

Uso: verificar_exp3.py <carpeta> [--deteccion URL] [--respuesta URL] [--bloqueo URL] [--prom URL] [--prefijo bot-]
La carpeta debe tener bitacora.csv y ejecucion.json (y, si existe, recuperacion_medida.json de medir_recuperacion.py).
Límites de los ASR: S-1 detección <= 100 ms (p95), S-2 recuperación <= 300 ms (p95)."""
import argparse, csv, json, math, pathlib, re, time, urllib.parse, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("carpeta")
ap.add_argument("--deteccion", default="http://localhost:30091")
ap.add_argument("--respuesta", default="http://localhost:30092")
ap.add_argument("--bloqueo", default="http://localhost:30090")
ap.add_argument("--prom", default="http://localhost:30900")
ap.add_argument("--prefijo", default="bot-")
ap.add_argument("--limite-deteccion-ms", type=float, default=100.0)
ap.add_argument("--limite-recuperacion-ms", type=float, default=300.0)
a = ap.parse_args()
carp = pathlib.Path(a.carpeta)
LIM_DET, LIM_REC = a.limite_deteccion_ms, a.limite_recuperacion_ms
LEGIT = ("NORMAL", "CONF_MISMO_ASIENTO", "CONF_GRUPOS_CRUZADOS", "CONF_VENDIDO", "CONF_MISMO_ASIENTO_SIN_VENDIDOS")

def get(url, t=60):
    with urllib.request.urlopen(url, timeout=t) as r: return json.load(r)
def p(v, pc):
    v = sorted(v)
    if not v: return None
    k = (len(v) - 1) * pc; f, c = math.floor(k), math.ceil(k)
    return v[int(k)] if f == c else v[f] + (v[c] - v[f]) * (k - f)
def r1(x): return None if x is None else round(x, 2)

ej = json.loads((carp / "ejecucion.json").read_text())
ex = ej.get("exp3")
if not ex: raise SystemExit("ejecucion.json no tiene la sección exp3: la corrida no tuvo ataques")
t0 = ej["inicio_epoch_ms"]
VENT = {"normal": (t0 + ex["ataque_normal_desde_s"] * 1000, t0 + ej["calentamiento_s"] * 1000),
        "pico": (t0 + (ej["calentamiento_s"] + ej["rampa_s"]) * 1000, t0 + (ej["calentamiento_s"] + ej["trafico_s"]) * 1000)}
ataques = {x["id"]: x for x in ex["ataques"]}
TIPOS = ("bot_individual", "granja_cuentas", "acaparador")
def ataque_de(cuenta):
    m = re.match(r"bot-(A\d+)-\d+$", cuenta)
    return m.group(1) if m and m.group(1) in ataques else None
def tipo_inyectado(cuenta):
    aid = ataque_de(cuenta)
    return ataques[aid].get("tipo", "bot_individual") if aid else None      # corridas anteriores a los tipos: todo era bot_individual
def etiqueta_auditoria(marca):
    """Etiqueta tipo_atacante que el detector copió a la evidencia (la declaró el generador; el detector no la calcula)."""
    d = json.loads(marca["detalle"]) if isinstance(marca.get("detalle"), str) else (marca.get("detalle") or {})
    return marca.get("tipo_atacante") or d.get("tipo_atacante") or "sin_etiqueta"
def fase_de(cuenta):
    m = re.match(r"bot-(A\d+)-\d+$", cuenta)
    return ataques[m.group(1)]["fase"] if m and m.group(1) in ataques else None

# ---------- 1) bitácora del generador
bots, legit, legit_cuentas = {}, [], set()
with open(carp / "bitacora.csv") as f:
    for r in csv.DictReader(f):
        ini, fin = int(r["t_inicio_ms"]), int(r["t_fin_ms"])
        if r["tipo"] == "ATAQUE_BOT":
            bots.setdefault(r["comprador"], []).append({"ini": ini, "fin": fin, "http": int(r["http"]), "res": r["resultado"], "asiento": r["asientos"], "grupo": r["grupo"], "ip": r.get("ip", "")})
        elif r["tipo"] in LEGIT:
            legit.append((ini, fin - ini, r["resultado"], r["comprador"]))
            legit_cuentas.add(r["comprador"])
bots_ok = {c: sum(1 for x in l if x["res"] == "OK") for c, l in bots.items()}
ordenes_obtenidas = sum(bots_ok.values())                  # solicitudes de bots que lograron retener asientos (= órdenes que deben cancelarse)
asientos_obtenidos = sum(len(x["asiento"].split("-")) for l in bots.values() for x in l if x["res"] == "OK")   # el acaparador retiene 4 por solicitud

# ---------- 2) bd_auditoria
aud, desde = [], 0
while True:
    pag = get(f"{a.deteccion}/deteccion/auditoria?desde={desde}&limite=5000")
    aud += pag
    if len(pag) < 5000: break
    desde = pag[-1]["id"]
marcas = {}
for x in aud:
    if x["tipo"] == "ATAQUE_DETECTADO": marcas.setdefault(x["cuenta"], x)
rec_int = {x["cuenta"]: json.loads(x["detalle"]) for x in aud if x["tipo"] == "RECUPERACION_COMPLETA"}
liberados_aud = sum(len(json.loads(x["detalle"]).get("asientos_liberados", [])) for x in aud if x["tipo"] == "ASIENTOS_LIBERADOS")
legit_marcados = sorted(c for c in marcas if not c.startswith(a.prefijo))

# ---------- 3) estado final
resumen = get(f"{a.respuesta}/respuesta/resumen?prefijo={urllib.parse.quote(a.prefijo)}")
estado = get(f"{a.bloqueo}/bloqueo/estado", 120)
bloq_bots = [b for b in estado["bloqueados"] if b["comprador"].startswith(a.prefijo)]

# ---------- 4) ataques y bots
det_ms = {"normal": [], "pico": []}
rec_int_ms = {"normal": [], "pico": []}
antes_marca, por_ataque = [], []
for aid, at in ataques.items():
    ids = [c for c in bots if c.startswith(f"bot-{aid}-")]
    marcados = [c for c in ids if c in marcas]
    for c in marcados:
        x = marcas[c]; d = x["ts_evidencia"] - x["ts_evento_detector"]
        det_ms[at["fase"]].append(d)
        pasaron = sum(1 for q in bots[c] if q["ini"] <= x["ts_evidencia"])
        antes_marca.append(pasaron)
        if c in rec_int: rec_int_ms[at["fase"]].append(rec_int[c]["ms_total_desde_alerta"])
    por_ataque.append({"id": aid, "fase": at["fase"], "bots_que_enviaron": len(ids), "bots_marcados": len(marcados),
                       "detectado": len(marcados) > 0, "completo": len(ids) > 0 and len(marcados) == len(ids)})
n_ataques = len(por_ataque)
todos_detectados = all(x["detectado"] for x in por_ataque)
todos_completos = all(x["completo"] for x in por_ataque)

# medida independiente (medir_recuperacion.py)
rec_ind = {"normal": [], "pico": []}; incompletas = 0; ventanas_rec = []
fm = carp / "recuperacion_medida.json"
medida = json.loads(fm.read_text()) if fm.exists() else None
if medida:
    for m in medida["mediciones"]:
        if m["completo"]:
            fz = fase_de(m["cuenta"])
            if fz: rec_ind[fz].append(m["recuperacion_ms"])
            ventanas_rec.append((m["t_alerta_ms"], m["t_fin_ms"] + 500))
        else: incompletas += 1
    incompletas += len(medida.get("sin_completar", []))
else:
    ventanas_rec = [(x["ts_evento_detector"], x["ts_evento_detector"] + rec_int.get(c, {}).get("ms_total_desde_alerta", 300) + 500) for c, x in marcas.items()]

# ---------- 4b) consistencia por tipo etiquetado (el tipo lo DECLARA el generador; no hay clasificador)
tipos_inyectados = [t for t in TIPOS if any(x.get("tipo", "bot_individual") == t for x in ataques.values())]
for x in por_ataque: x["tipo"] = ataques[x["id"]].get("tipo", "bot_individual")
por_tipo = {}
for t in tipos_inyectados:
    ids = [aid for aid, at in ataques.items() if at.get("tipo", "bot_individual") == t]
    ctas = [c for c in bots if tipo_inyectado(c) == t]
    marc = [c for c in ctas if c in marcas]
    ant = [sum(1 for q in bots[c] if q["ini"] <= marcas[c]["ts_evidencia"]) for c in marc]
    dms = [marcas[c]["ts_evidencia"] - marcas[c]["ts_evento_detector"] for c in marc]
    r_i = [m["recuperacion_ms"] for m in (medida["mediciones"] if medida else []) if m["completo"] and tipo_inyectado(m["cuenta"]) == t]
    r_a = [rec_int[c]["ms_total_desde_alerta"] for c in marc if c in rec_int]
    reglas = [json.loads(marcas[c]["detalle"]).get("regla") for c in marc]
    det_ids = [x["id"] for x in por_ataque if x["tipo"] == t and x["detectado"]]
    por_tipo[t] = {"ataques_inyectados": len(ids), "ataques_detectados": len(det_ids), "todos_detectados": len(det_ids) == len(ids),
                   "actores_inyectados": len(ctas), "actores_marcados": len(marc),
                   "reglas": {r: reglas.count(r) for r in sorted(set(reglas))},
                   "etiqueta_en_auditoria_coincide": sum(1 for c in marc if etiqueta_auditoria(marcas[c]) == t),
                   "solicitudes_fraudulentas_antes_de_la_marca": {"promedio": r1(sum(ant) / len(ant)) if ant else None, "p95": p(ant, .95), "max": max(ant) if ant else None},
                   "deteccion_p95_ms_auditoria": r1(p(dms, .95)), "recuperacion_p95_ms_medida_independiente": r1(p(r_i, .95)),
                   "recuperacion_p95_ms_interna_auditoria": r1(p(r_a, .95)), "n_recuperaciones_medidas": len(r_i),
                   "S1_cumple_auditoria": None if not dms else p(dms, .95) <= LIM_DET,
                   "S2_cumple": None if not (r_i or r_a) else p(r_i if r_i else r_a, .95) <= LIM_REC}
todos_tipos_detectados = bool(por_tipo) and all(v["todos_detectados"] for v in por_tipo.values())

# ---------- 5) tráfico legítimo durante las ventanas de recuperación
def en_ventana(t): return any(i <= t <= f for i, f in ventanas_rec)
trafico = {}
for fz, (i, f) in VENT.items():
    dentro = [ms for t, ms, res, c in legit if i <= t <= f and en_ventana(t)]
    fuera = [ms for t, ms, res, c in legit if i <= t <= f and not en_ventana(t)]
    trafico[fz] = {"n_durante_recuperacion": len(dentro), "p95_durante_recuperacion_ms": r1(p(dentro, .95)),
                   "n_fuera": len(fuera), "p95_fuera_ms": r1(p(fuera, .95))}
legit_revocados = sum(1 for t, ms, res, c in legit if res == "CUENTA_REVOCADA")
legit_errores = sum(1 for t, ms, res, c in legit if res not in ("OK", "NO_DISPONIBLE", "CUENTA_REVOCADA"))

# ---------- 6) Prometheus (con el desfase de reloj entre Prometheus y esta máquina)
prom = {}
try:
    _a = time.time(); _s = float(get(f"{a.prom}/api/v1/query?query=vector(time())")["data"]["result"][0]["value"][1]); _b = time.time()
    OFF = _s - (_a + _b) / 2
    def q(expr, t):
        u = a.prom + "/api/v1/query?" + urllib.parse.urlencode({"query": expr, "time": f"{t / 1000 + OFF:.3f}"})
        r = get(u)["data"]["result"]
        return float(r[0]["value"][1]) if r and r[0]["value"][1] not in ("NaN", "+Inf") else None
    for fz, (i, f) in VENT.items():
        fin = f + 25000            # margen para detecciones y recuperaciones de los ataques del final de la ventana
        w = int((fin - i) / 1000)
        det_p95 = q(f"histogram_quantile(0.95, sum(increase(taq_deteccion_seconds_bucket[{w}s])) by (le))", fin)
        rec_p95 = q(f"histogram_quantile(0.95, sum(increase(taq_recuperacion_seconds_bucket[{w}s])) by (le))", fin)
        n_det = q(f"sum(increase(taq_deteccion_seconds_count[{w}s]))", fin)
        n_rec = q(f"sum(increase(taq_recuperacion_seconds_count[{w}s]))", fin)
        le_det = q(f'sum(increase(taq_deteccion_seconds_bucket{{le="0.1"}}[{w}s]))', fin)
        le_rec = q(f'sum(increase(taq_recuperacion_seconds_bucket{{le="0.3"}}[{w}s]))', fin)
        wv = int((f - i) / 1000)
        prom[fz] = {"deteccion_p95_ms": r1(det_p95 * 1000) if det_p95 is not None else None, "detecciones": n_det,
                    "deteccion_pct_le_100ms": r1(100 * le_det / n_det) if n_det and le_det is not None else None,
                    "recuperacion_p95_ms": r1(rec_p95 * 1000) if rec_p95 is not None else None, "recuperaciones": n_rec,
                    "recuperacion_pct_le_300ms": r1(100 * le_rec / n_rec) if n_rec and le_rec is not None else None,
                    "cola_evento_trafico_max": q(f"max_over_time(max(taq_cola_evento_trafico_profundidad)[{wv}s:5s])", f),
                    "cola_operacion_max": q(f"max_over_time(max(taq_cola_operacion_profundidad)[{wv}s:2s])", f),
                    "cola_alerta_max": q(f"max_over_time(max(taq_cola_alerta_profundidad)[{wv}s:2s])", f),
                    "eventos_descartados": q(f"sum(increase(taq_eventos_trafico_descartados_total[{wv}s]))", f),
                    "rechazos_cuenta_revocada": q(f"sum(increase(taq_rechazos_cuenta_revocada_total[{wv}s]))", f)}
    fin_t = VENT["pico"][1] + 25000; w_t = int((fin_t - VENT["normal"][0]) / 1000)
    prom["por_tipo"] = {}
    for t in tipos_inyectados:
        dp = q(f'histogram_quantile(0.95, sum(increase(taq_deteccion_seconds_bucket{{tipo="{t}"}}[{w_t}s])) by (le))', fin_t)
        rp = q(f'histogram_quantile(0.95, sum(increase(taq_recuperacion_seconds_bucket{{tipo="{t}"}}[{w_t}s])) by (le))', fin_t)
        prom["por_tipo"][t] = {"deteccion_p95_ms": r1(dp * 1000) if dp is not None else None, "recuperacion_p95_ms": r1(rp * 1000) if rp is not None else None,
                               "marcas_por_tipo_total": q(f'sum(taq_ataques_detectados_total{{tipo="{t}"}})', fin_t)}
        por_tipo[t]["deteccion_p95_ms_prometheus"] = prom["por_tipo"][t]["deteccion_p95_ms"]
        por_tipo[t]["recuperacion_p95_ms_prometheus"] = prom["por_tipo"][t]["recuperacion_p95_ms"]
    prom["sospechosas_total"] = q("sum(taq_cuentas_sospechosas_total)", VENT["pico"][1] + 25000)
    # Series completas de la corrida como evidencia (junto al tablero de Grafana)
    (carp / "prometheus").mkdir(exist_ok=True)
    ini_s, fin_s = t0 / 1000 - 30 + OFF, VENT["pico"][1] / 1000 + 90 + OFF
    for nombre, expr in {"deteccion_p95": "histogram_quantile(0.95, sum(rate(taq_deteccion_seconds_bucket[1m])) by (le))",
                         "recuperacion_p95": "histogram_quantile(0.95, sum(rate(taq_recuperacion_seconds_bucket[1m])) by (le))",
                         "cola_evento_trafico": "max(taq_cola_evento_trafico_profundidad)", "cola_operacion": "max(taq_cola_operacion_profundidad)",
                         "reservar_p95": "histogram_quantile(0.95, sum(rate(taq_reservar_seconds_bucket[30s])) by (le))",
                         "cuentas_sospechosas": "sum(taq_cuentas_sospechosas_total)"}.items():
        u = a.prom + "/api/v1/query_range?" + urllib.parse.urlencode({"query": expr, "start": f"{ini_s:.3f}", "end": f"{fin_s:.3f}", "step": 5})
        (carp / "prometheus" / f"{nombre}.json").write_text(json.dumps(get(u)["data"]["result"]))
except Exception as e:
    prom = {"error": f"no se pudo consultar Prometheus: {e}"}

# ---------- 7) veredictos
def cumple(valor, lim): return None if valor is None else valor <= lim
V = {}
for fz in ("normal", "pico"):
    d_aud, d_prom = p(det_ms[fz], .95), (prom.get(fz) or {}).get("deteccion_p95_ms")
    r_ind, r_int, r_prom = p(rec_ind[fz], .95), p(rec_int_ms[fz], .95), (prom.get(fz) or {}).get("recuperacion_p95_ms")
    V[fz] = {"S1_deteccion_p95_ms_prometheus": d_prom, "S1_deteccion_p95_ms_auditoria": r1(d_aud), "S1_cumple": cumple(d_prom if d_prom is not None else d_aud, LIM_DET),
             "S2_recuperacion_p95_ms_medida_independiente": r1(r_ind), "S2_recuperacion_p95_ms_interna_auditoria": r1(r_int),
             "S2_recuperacion_p95_ms_prometheus": r_prom, "S2_cumple": cumple(r_ind if r_ind is not None else (r_int if r_int is not None else r_prom), LIM_REC),
             "n_detecciones_auditoria": len(det_ms[fz]), "n_recuperaciones_medidas": len(rec_ind[fz])}
bots_total = len(bots)
criterios = {
    "todos_los_ataques_detectados": todos_detectados,
    "todos_los_bots_marcados": todos_completos,
    "compradores_legitimos_marcados_0": len(legit_marcados) == 0,
    "cuentas_legitimas_revocadas_0": resumen["revocadas_postgres_otras"] == 0 and legit_revocados == 0,
    "asientos_de_bots_retenidos_al_final_0": len(bloq_bots) == 0,
    "asientos_liberados_igual_a_los_obtenidos": liberados_aud == asientos_obtenidos,
    "ordenes_canceladas_igual_a_los_obtenidos": resumen["ordenes_canceladas_bots"] == ordenes_obtenidas,
    "cuentas_revocadas_igual_a_bots": resumen["revocadas_postgres_bots"] == bots_total and resumen["revocadas_redis"] >= bots_total,
    "todos_los_ataques_de_cada_tipo_detectados": todos_tipos_detectados,
    "S1_p95_dentro_del_limite": all(V[fz]["S1_cumple"] for fz in V if V[fz]["S1_cumple"] is not None) and any(V[fz]["S1_cumple"] is not None for fz in V),
    "S2_p95_dentro_del_limite": all(V[fz]["S2_cumple"] for fz in V if V[fz]["S2_cumple"] is not None) and any(V[fz]["S2_cumple"] is not None for fz in V),
}
out = {"carpeta": str(carp), "limites_ms": {"S1": LIM_DET, "S2": LIM_REC}, "ataques": n_ataques, "bots": bots_total,
       "solicitudes_de_bots": sum(len(l) for l in bots.values()), "asientos_obtenidos_por_bots": asientos_obtenidos, "ordenes_obtenidas_por_bots": ordenes_obtenidas,
       "por_ataque": por_ataque, "tipos_de_ataque": {"nota": "el tipo lo declara el generador (etiqueta tipoAtacante); no hay clasificador", "por_tipo": por_tipo},
       "solicitudes_fraudulentas_antes_de_la_marca": {"promedio": r1(sum(antes_marca) / len(antes_marca)) if antes_marca else None,
       "p95": p(antes_marca, .95), "max": max(antes_marca) if antes_marca else None},
       "compradores_legitimos_marcados": legit_marcados, "asientos_liberados_auditoria": liberados_aud, "resumen_respuesta": resumen,
       "asientos_de_bots_aun_bloqueados": len(bloq_bots), "veredictos_por_fase": V, "prometheus": prom, "trafico_legitimo": trafico,
       "legitimos_con_cuenta_revocada": legit_revocados, "legitimos_con_error_tecnico": legit_errores,
       "recuperaciones_no_completadas_en_medicion": incompletas, "hay_medida_independiente": medida is not None, "criterios": criterios,
       "cumple_todo": all(criterios.values())}
(carp / "verificacion.json").write_text(json.dumps(out, indent=1))

mk = lambda b: "n/d" if b is None else ("✅" if b else "❌")
f1 = lambda v: "n/d" if v is None else (f"{v:.1f}" if isinstance(v, float) else str(v))
L = ["# EXP-3 — verificación de la corrida", "", f"**Resultado global: {'✅ cumple' if out['cumple_todo'] else '❌ no cumple (ver criterios)'}**", "",
     f"{n_ataques} ataques, {bots_total} bots, {out['solicitudes_de_bots']} solicitudes de bots, {asientos_obtenidos} asientos retenidos por bots.", "",
     "## Criterios", "", "| Criterio | Resultado |", "|---|---|"]
for k, v in criterios.items(): L.append(f"| {k.replace('_', ' ')} | {mk(v)} |")
L += ["", f"## S-1 detección (límite {LIM_DET:.0f} ms) y S-2 recuperación (límite {LIM_REC:.0f} ms), p95 por fase", "",
      "| Fase | Detección p95 Prometheus | Detección p95 auditoría | Recuperación p95 medida independiente | Recuperación p95 interna (auditoría) | Recuperación p95 Prometheus |", "|---|---|---|---|---|---|"]
for fz, v in V.items():
    L.append(f"| {fz} | {f1(v['S1_deteccion_p95_ms_prometheus'])} ms {mk(v['S1_cumple'])} | {f1(v['S1_deteccion_p95_ms_auditoria'])} ms | "
             f"{f1(v['S2_recuperacion_p95_ms_medida_independiente'])} ms {mk(v['S2_cumple'])} | {f1(v['S2_recuperacion_p95_ms_interna_auditoria'])} ms | {f1(v['S2_recuperacion_p95_ms_prometheus'])} ms |")
L += ["", "La detección de Prometheus incluye el INSERT en bd_auditoria; la de la auditoría resta el instante previo al INSERT (por eso es algo menor).", ""]
L += ["## Tipos de ataque", "", "El tipo lo **declara el generador** con la etiqueta `tipoAtacante` (no hay clasificador): esta tabla comprueba que cada tipo etiquetado se detectó con la regla esperada y mide S-1 y S-2 por tipo.", "",
      "| Tipo | Ataques (detectados / inyectados) | Cuentas (marcadas / inyectadas) | Regla que disparó cada marca | Etiqueta en auditoría coincide | Solicitudes antes de la marca (prom / p95 / máx) | Detección p95 (auditoría / Prometheus) | Recuperación p95 (independiente / interna / Prometheus) |", "|---|---|---|---|---|---|---|---|"]
for t, v in por_tipo.items():
    sf = v["solicitudes_fraudulentas_antes_de_la_marca"]
    L.append(f"| {t} | {v['ataques_detectados']} / {v['ataques_inyectados']} {mk(v['todos_detectados'])} | {v['actores_marcados']} / {v['actores_inyectados']} | {', '.join(f'{r}={n}' for r, n in v['reglas'].items()) or '-'} | {v['etiqueta_en_auditoria_coincide']} / {v['actores_marcados']} | "
             f"{f1(sf['promedio'])} / {f1(sf['p95'])} / {f1(sf['max'])} | {f1(v['deteccion_p95_ms_auditoria'])} ms {mk(v['S1_cumple_auditoria'])} / {f1(v.get('deteccion_p95_ms_prometheus'))} ms | "
             f"{f1(v['recuperacion_p95_ms_medida_independiente'])} ms {mk(v['S2_cumple'])} / {f1(v['recuperacion_p95_ms_interna_auditoria'])} ms / {f1(v.get('recuperacion_p95_ms_prometheus'))} ms |")
L += ["", f"Compradores legítimos marcados: {len(legit_marcados)} (cuentas legítimas observadas: {len(legit_cuentas)}).", ""]
L += ["## Ataques", "", "| Ataque | Fase | Tipo | Bots | Marcados | Detectado | Completo |", "|---|---|---|---|---|---|---|"]
for x in por_ataque: L.append(f"| {x['id']} | {x['fase']} | {x['tipo']} | {x['bots_que_enviaron']} | {x['bots_marcados']} | {mk(x['detectado'])} | {mk(x['completo'])} |")
sa = out["solicitudes_fraudulentas_antes_de_la_marca"]
L += ["", "## Datos adicionales", "",
      f"- Solicitudes fraudulentas por bot que pasaron antes de la marca: promedio {f1(sa['promedio'])}, p95 {f1(sa['p95'])}, máx {f1(sa['max'])}.",
      f"- Compradores legítimos marcados: {len(legit_marcados)} {legit_marcados[:5] or ''}; legítimos con respuesta CUENTA_REVOCADA: {legit_revocados}; errores técnicos de legítimos: {legit_errores}.",
      f"- Asientos obtenidos por bots {asientos_obtenidos} · liberados (auditoría) {liberados_aud} · aún bloqueados al final {len(bloq_bots)}.",
      f"- Órdenes obtenidas por bots {ordenes_obtenidas} · canceladas (bots / otras): {resumen['ordenes_canceladas_bots']} / {resumen['ordenes_canceladas_otras']} · cuentas revocadas Postgres (bots / otras): {resumen['revocadas_postgres_bots']} / {resumen['revocadas_postgres_otras']} · Redis: {resumen['revocadas_redis']}.",
      f"- Medida independiente de recuperación: {'sí' if medida else 'NO (falta recuperacion_medida.json)'}; seguimientos sin completar: {incompletas}.", "",
      "## Tráfico legítimo (p95 de reservar, bitácora del generador)", "", "| Fase | Durante recuperaciones (n) | p95 durante | Fuera de recuperaciones (n) | p95 fuera |", "|---|---|---|---|---|"]
for fz, t in trafico.items():
    L.append(f"| {fz} | {t['n_durante_recuperacion']} | {f1(t['p95_durante_recuperacion_ms'])} ms | {t['n_fuera']} | {f1(t['p95_fuera_ms'])} ms |")
if "error" in prom: L += ["", f"**Prometheus:** {prom['error']}"]
else:
    L += ["", "## Colas y descartes (Prometheus)", "", "| Fase | cola_evento_trafico máx | cola_operacion máx | cola_alerta máx | eventos descartados | rechazos cuenta revocada |", "|---|---|---|---|---|---|"]
    for fz in ("normal", "pico"):
        v = prom[fz]; L.append(f"| {fz} | {f1(v['cola_evento_trafico_max'])} | {f1(v['cola_operacion_max'])} | {f1(v['cola_alerta_max'])} | {f1(v['eventos_descartados'])} | {f1(v['rechazos_cuenta_revocada'])} |")
(carp / "verificacion.md").write_text("\n".join(L) + "\n")
print("\n".join(L[:12]))
print("escrito:", carp / "verificacion.md")
raise SystemExit(0 if out["cumple_todo"] else 1)
