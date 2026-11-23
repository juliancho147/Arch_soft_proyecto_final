#!/usr/bin/env python3
"""EXP-3 desde el panel: ataques de reventa de los 3 tipos del plan, en cantidad y momentos ALEATORIOS, con medición de S-1 y S-2.

Tipos (cada uno lo delata una señal distinta; el tipo viaja como etiqueta `tipoAtacante` en el JSON de la solicitud, no hay clasificador):
  bot_individual  100 bots, cada uno con su IP y su cuenta, ~10 reservas/min          -> regla cuenta_frecuencia
  granja_cuentas  100 cuentas detrás de UNA IP, ~3 reservas/min por cuenta            -> regla ip_frecuencia / ip_marcada
  acaparador      20 cuentas (IP propia) que piden 4 asientos distintos, ~5 por min   -> regla cuenta_asientos
Solo biblioteca estándar. Lo usa servidor.py."""
import json, os, random, threading, time, urllib.parse, urllib.request
from datetime import datetime

GATEWAY = os.environ.get("TAQ_GATEWAY", "http://localhost:30080")
PROM = os.environ.get("TAQ_PROM", "http://localhost:30900")
LIM_S1_MS, LIM_S2_MS = 100, 300
TIPOS = {
    "bot_individual": dict(nombre="Bot individual", cuentas=100, por_min=10, asientos=1, ip_unica=False, max_por_cuenta=10),
    "granja_cuentas": dict(nombre="Granja de cuentas", cuentas=100, por_min=3, asientos=1, ip_unica=True, max_por_cuenta=3),
    "acaparador": dict(nombre="Acaparador de asientos", cuentas=20, por_min=5, asientos=4, ip_unica=False, max_por_cuenta=5),
}
DURACION_MAX_ATAQUE_S = 60        # un atacante deja de insistir tras este tiempo si no lo revocan
COMIENZO_ASIENTOS = 200001        # rango de asientos exclusivo de atacantes (el catálogo llega a 400.000)
FIN_ASIENTOS = 390000

lock = threading.Lock()
E = {"activo": False, "inicio": 0.0, "fin": 0.0, "duracion_s": 0, "programados": 0, "ataques": [], "base": {}, "resumen": None, "hilo": None}
_sig_asiento = [COMIENZO_ASIENTOS]
_n_ataque = [0]

def _post(cuerpo, ip):
    req = urllib.request.Request(GATEWAY + "/api/reservar", json.dumps(cuerpo).encode(),
                                 {"Content-Type": "application/json", "X-Forwarded-For": ip})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except Exception: return e.code, {}
    except Exception:
        return 0, {}

def _asientos(n):
    with lock:
        ini = _sig_asiento[0]; _sig_asiento[0] += n
        if _sig_asiento[0] > FIN_ASIENTOS: _sig_asiento[0] = COMIENZO_ASIENTOS
    return list(range(ini, ini + n))

def prom(q):
    try:
        with urllib.request.urlopen(PROM + "/api/v1/query?query=" + urllib.parse.quote(q), timeout=4) as r:
            res = json.loads(r.read())["data"]["result"]
            return [(x["metric"], float(x["value"][1])) for x in res]
    except Exception:
        return []

def _uno(q):
    r = prom(q)
    return r[0][1] if r and r[0][1] == r[0][1] else None

# ---------------------------------------------------------------- un ataque
def _lanzar_ataque(tipo, rnd):
    cfg = TIPOS[tipo]
    with lock:
        _n_ataque[0] += 1; n = _n_ataque[0]
    reg = dict(id=f"A{n}", n=n, tipo=tipo, nombre=cfg["nombre"], hora=datetime.now().strftime("%H:%M:%S"), t0=time.time(), cuentas=cfg["cuentas"],
               solicitudes=0, ok=0, bloqueadas=0, otras=0, terminados=0, terminado=False)
    with lock: E["ataques"].append(reg)
    ip_granja = f"198.51.{n % 250}.1"
    def cuenta_loop(i):
        cuenta = f"bot-P{n}-{i}"
        ip = ip_granja if cfg["ip_unica"] else (f"203.0.{n % 250}.{i}" if tipo == "bot_individual" else f"100.64.{n % 250}.{i}")
        paso = 60.0 / cfg["por_min"]
        time.sleep(rnd.uniform(0, paso))                      # los atacantes no arrancan sincronizados
        enviadas = 0; ini = time.time()
        while E["activo"] and enviadas < cfg["max_por_cuenta"] and time.time() - ini < DURACION_MAX_ATAQUE_S:
            asientos = _asientos(cfg["asientos"])
            http, r = _post({"solicitudId": f"AT{n}-{i}-{enviadas}", "comprador": cuenta, "evento": 1, "asientos": asientos, "tipoAtacante": tipo}, ip)
            enviadas += 1
            res = r.get("resultado", "ERROR")
            with lock:
                reg["solicitudes"] += 1
                if res == "OK": reg["ok"] += 1
                elif res == "CUENTA_REVOCADA" or http == 403: reg["bloqueadas"] += 1
                else: reg["otras"] += 1
            if res == "CUENTA_REVOCADA" or http == 403: break      # revocada: el atacante deja de insistir
            time.sleep(max(0.2, paso * rnd.uniform(0.85, 1.15)))
        with lock:
            reg["terminados"] += 1
            if reg["terminados"] >= reg["cuentas"]: reg["terminado"] = True; reg["t1"] = time.time()
    for i in range(1, cfg["cuentas"] + 1):
        threading.Thread(target=cuenta_loop, args=(i,), daemon=True).start()

# ---------------------------------------------------------------- la prueba completa
def _base():
    """Valores acumulados de Prometheus al iniciar; el resumen usa la diferencia (así no hace falta reiniciar el sistema antes)."""
    b = {}
    for tipo in TIPOS: b["marcadas_" + tipo] = _uno(f'sum(taq_ataques_detectados_total{{tipo="{tipo}"}})') or 0.0
    for k, q in dict(liberados="sum(taq_bloqueo_liberados_ataque_total)", ordenes="sum(taq_ordenes_canceladas_total)", revocadas="sum(taq_cuentas_revocadas_total)",
                     falsos="sum(taq_marcas_falsos_positivos_total)", antes_sum="sum(taq_solicitudes_fraudulentas_antes_de_marca_sum)",
                     antes_n="sum(taq_solicitudes_fraudulentas_antes_de_marca_count)").items():
        b[k] = _uno(q) or 0.0
    return b

def iniciar(duracion_s, semilla=None, minimo=None, maximo=None):
    """Programa N ataques aleatorios (N, momento y tipo al azar) dentro de duracion_s. Devuelve el plan, o None si ya hay una prueba."""
    with lock:
        if E["activo"]: return None
        E.update(activo=True, inicio=time.time(), fin=time.time() + duracion_s, duracion_s=duracion_s, ataques=[], resumen=None)
    rnd = random.Random(semilla)
    minutos = duracion_s / 60.0
    lo = minimo if minimo is not None else 2
    hi = maximo if maximo is not None else max(lo + 1, min(30, int(2 + 2 * minutos)))
    n = rnd.randint(lo, hi)
    cola = 75 if duracion_s >= 150 else 30            # tiempo final para que el último ataque alcance a detectarse y recuperarse
    desde, hasta = 10, max(20, duracion_s - cola)
    momentos = sorted(rnd.uniform(desde, hasta) for _ in range(n))
    plan = [(round(t, 1), rnd.choice(list(TIPOS))) for t in momentos]
    with lock: E["programados"] = n; E["plan"] = plan; E["base"] = _base()
    def corre():
        t0 = E["inicio"]
        for t, tipo in plan:
            while E["activo"] and time.time() - t0 < t: time.sleep(0.2)
            if not E["activo"]: break
            _lanzar_ataque(tipo, rnd)
        while E["activo"] and time.time() < E["fin"]: time.sleep(0.5)
        detener(auto=True)
    th = threading.Thread(target=corre, daemon=True); th.start(); E["hilo"] = th
    return plan

def detener(auto=False):
    with lock:
        if not E["activo"]: return
        E["activo"] = False
    time.sleep(1.0)
    E["resumen"] = resumen()

# ---------------------------------------------------------------- medición
def medir():
    """p95 y contadores de S-1 y S-2 durante la prueba (diferencias respecto a la base)."""
    w = int((time.time() - E["inicio"]) + 15) if E["inicio"] else 60
    q95 = lambda m, extra="": _uno(f'histogram_quantile(0.95, sum(increase({m}_bucket{extra}[{w}s])) by (le))')
    det, rec = q95("taq_deteccion_seconds"), q95("taq_recuperacion_seconds")
    out = dict(p95_deteccion_ms=None if det is None else det * 1000, p95_recuperacion_ms=None if rec is None else rec * 1000, por_tipo={})
    b = E.get("base", {})
    for tipo in TIPOS:
        marc = (_uno(f'sum(taq_ataques_detectados_total{{tipo="{tipo}"}})') or 0.0) - b.get("marcadas_" + tipo, 0.0)
        d = q95("taq_deteccion_seconds", f'{{tipo="{tipo}"}}'); r_ = q95("taq_recuperacion_seconds", f'{{tipo="{tipo}"}}')
        with lock:
            inyectadas = sum(a["cuentas"] for a in E["ataques"] if a["tipo"] == tipo)
            ataques = sum(1 for a in E["ataques"] if a["tipo"] == tipo)
        out["por_tipo"][tipo] = dict(nombre=TIPOS[tipo]["nombre"], ataques=ataques, cuentas_inyectadas=inyectadas, cuentas_marcadas=round(max(0, marc)),
                                     p95_deteccion_ms=None if d is None else d * 1000, p95_recuperacion_ms=None if r_ is None else r_ * 1000)
    cur = lambda q, k: round(max(0.0, (_uno(q) or 0.0) - b.get(k, 0.0)))
    out["asientos_liberados"] = cur("sum(taq_bloqueo_liberados_ataque_total)", "liberados")
    out["ordenes_canceladas"] = cur("sum(taq_ordenes_canceladas_total)", "ordenes")
    out["cuentas_revocadas"] = cur("sum(taq_cuentas_revocadas_total)", "revocadas")
    out["legitimos_marcados"] = cur("sum(taq_marcas_falsos_positivos_total)", "falsos")
    an = (_uno("sum(taq_solicitudes_fraudulentas_antes_de_marca_sum)") or 0.0) - b.get("antes_sum", 0.0)
    nn = (_uno("sum(taq_solicitudes_fraudulentas_antes_de_marca_count)") or 0.0) - b.get("antes_n", 0.0)
    out["solicitudes_antes_de_marca"] = (an / nn) if nn > 0 else None
    out["s1_cumple"] = None if det is None else det * 1000 <= LIM_S1_MS
    out["s2_cumple"] = None if rec is None else rec * 1000 <= LIM_S2_MS
    return out

def estado():
    with lock:
        activo, ini, fin = E["activo"], E["inicio"], E["fin"]
        ataques = [dict(a) for a in E["ataques"]]
        res = E["resumen"]
        prog = E["programados"]
    m = medir() if (activo or ataques) else None
    return dict(activo=activo, restante=max(0, round(fin - time.time())) if activo else 0, transcurrido=round(time.time() - ini) if ini and activo else 0,
                programados=prog, lanzados=len(ataques), ataques=ataques[::-1][:25], medidas=m, resumen_listo=res is not None,
                limites=dict(s1=LIM_S1_MS, s2=LIM_S2_MS))

def resumen():
    m = medir()
    with lock:
        ataques = [dict(a) for a in E["ataques"]]; dur = E["duracion_s"]
    f = lambda v, d=1: "n/d" if v is None else f"{v:.{d}f}"
    L = ["# Experimento 3 desde el panel — resumen de la prueba", "",
         f"- Duración: **{dur // 60} min {dur % 60} s** · ataques lanzados (cantidad y momentos aleatorios): **{len(ataques)}** · "
         f"cuentas atacantes inyectadas: **{sum(a['cuentas'] for a in ataques)}**",
         f"- **S-1, p95 de detección: {f(m['p95_deteccion_ms'])} ms** (límite {LIM_S1_MS} ms) → "
         f"{'✅ cumple' if m['s1_cumple'] else ('❌ NO cumple' if m['s1_cumple'] is not None else 'sin datos')}",
         f"- **S-2, p95 de recuperación: {f(m['p95_recuperacion_ms'])} ms** (límite {LIM_S2_MS} ms) → "
         f"{'✅ cumple' if m['s2_cumple'] else ('❌ NO cumple' if m['s2_cumple'] is not None else 'sin datos')}",
         f"- Compradores legítimos marcados: **{m['legitimos_marcados']}** (se espera 0) · asientos liberados {m['asientos_liberados']} · "
         f"órdenes canceladas {m['ordenes_canceladas']} · cuentas revocadas {m['cuentas_revocadas']}",
         f"- Solicitudes fraudulentas que pasaron antes de la marca (promedio por cuenta): {f(m['solicitudes_antes_de_marca'])}", "",
         "## Por tipo de ataque (el tipo es la etiqueta `tipoAtacante` que declara el panel)", "",
         "| Tipo | Ataques | Cuentas inyectadas | Cuentas marcadas | p95 detección | p95 recuperación |", "|---|---|---|---|---|---|"]
    for t, v in m["por_tipo"].items():
        L.append(f"| {v['nombre']} | {v['ataques']} | {v['cuentas_inyectadas']} | {v['cuentas_marcadas']} | {f(v['p95_deteccion_ms'])} ms | {f(v['p95_recuperacion_ms'])} ms |")
    L += ["", "## Ataques lanzados", "", "| # | Hora | Tipo | Cuentas | Solicitudes | OK | Rechazadas por cuenta revocada |", "|---|---|---|---|---|---|---|"]
    for a in ataques:
        L.append(f"| {a['id']} | {a['hora']} | {a['nombre']} | {a['cuentas']} | {a['solicitudes']} | {a['ok']} | {a['bloqueadas']} |")
    L += ["", "> Resumen rápido del panel con las métricas de Prometheus. La verificación completa (bitácora x auditoría x estado final) la hace `exp3/scripts/verificar_exp3.py`.", ""]
    return "\n".join(L)

def resumen_md():
    return E["resumen"] or resumen()
