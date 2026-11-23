#!/usr/bin/env python3
"""Panel de control de EXP-1: tráfico normal parametrizable + inyección de compras simultáneas a demanda.
Solo biblioteca estándar. Uso: python3 servidor.py  →  http://localhost:8088"""
import json, os, random, subprocess, threading, time, urllib.parse, urllib.request
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GATEWAY = os.environ.get("TAQ_GATEWAY", "http://localhost:30080")
PROM = os.environ.get("TAQ_PROM", "http://localhost:30900")
PUERTO = int(os.environ.get("PUERTO", "8088"))
AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA_BASE = os.path.join(os.path.dirname(AQUI), "resultados", "panel")
LIM_ASR_MS = 150

lock = threading.Lock()
rnd = random.Random()
S = dict(modo="normal", fase="", auto_conflictos=False, corriendo=False, rpm=0, fin=0, inicio=0, enviadas=0, ok=0, canceladas=0, errores=0, confirmadas=0, abandonadas=0)
lat = deque()                       # (t, ms) últimas reservas, para el p95 del cliente
eventos = []                        # tarjetas de conflicto
serie = deque(maxlen=900)           # muestras cada 2 s
confirmados = []                    # sillas vendidas (para el conflicto "ya vendida")
frescas = list(range(1, 100001)); rnd.shuffle(frescas)
bloques_usados = set()
idsol = [0]; sesion = {"dir": None}

def post(ruta, cuerpo, timeout=15):
    t0 = time.time()
    req = urllib.request.Request(GATEWAY + ruta, json.dumps(cuerpo).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}"), (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        try: cuerpo_r = json.loads(e.read() or b"{}")
        except Exception: cuerpo_r = {}
        return e.code, cuerpo_r, (time.time() - t0) * 1000
    except Exception:
        return 0, {}, (time.time() - t0) * 1000

def nuevo_id():
    with lock:
        idsol[0] += 1; return f"P{idsol[0]}"

def reservar(comprador, asientos):
    http, r, ms = post("/api/reservar", {"solicitudId": nuevo_id(), "comprador": comprador, "evento": 1, "asientos": asientos})
    res = r.get("resultado", "ERROR")
    with lock:
        lat.append((time.time(), ms)); S["enviadas"] += 1
        if res == "OK": S["ok"] += 1
        elif res == "NO_DISPONIBLE": S["canceladas"] += 1
        else: S["errores"] += 1
    return res, r.get("motivo", ""), ms

def confirmar(comprador, asientos):
    http, r, ms = post("/api/confirmar", {"solicitudId": nuevo_id(), "comprador": comprador, "asientos": asientos})
    ok = r.get("resultado") == "OK"
    with lock:
        if ok: S["confirmadas"] += 1; confirmados.extend(asientos)
    return ok

# ---------- tráfico normal ----------
def llegada():
    with lock:
        if not frescas: return
        silla = frescas.pop()
    c = "n" + nuevo_id()
    res, _, _ = reservar(c, [silla])
    if res != "OK": return
    if rnd.random() < 0.70:
        time.sleep(5 + rnd.random() * 35)
        if S["corriendo"] or True: confirmar(c, [silla])
    else:
        with lock: S["abandonadas"] += 1       # el bloqueo vence solo a los 8 min

def bucle_trafico():
    while True:
        with lock:
            run, rpm, fin = S["corriendo"], S["rpm"], S["fin"]
        if not run: return
        if fin and time.time() >= fin:
            detener(); return
        if rpm <= 0: time.sleep(0.3); continue
        auto = S["auto_conflictos"]
        factor = (1 + 0.05 * 7.5) if auto else 1.0                 # los conflictos cuentan dentro de la tasa objetivo
        time.sleep(min(rnd.expovariate(rpm / factor / 60.0), 5))   # llegadas de Poisson
        with lock:
            if not S["corriendo"]: return
        threading.Thread(target=llegada, daemon=True).start()
        if auto and rnd.random() < 0.05:                           # 1 de cada 20 llegadas dispara un conflicto de 5 a 10
            threading.Thread(target=inyectar, args=(rnd.randint(5, 10), "aleatorio"), daemon=True).start()

def iniciar(rpm, duracion_s):
    with lock:
        if S["corriendo"]: return False
        if not sesion["dir"]:
            sesion["dir"] = os.path.join(SALIDA_BASE, "sesion-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
            os.makedirs(sesion["dir"], exist_ok=True)
        S.update(corriendo=True, rpm=rpm, inicio=time.time(), fin=(time.time() + duracion_s) if duracion_s else 0)
    threading.Thread(target=bucle_trafico, daemon=True).start()
    return True

def rampa(pico_min, tasa_pico=8000, tasa_base=400, calent_s=60, rampa_s=120):
    """EXP-2: calentamiento a tasa_base, rampa lineal a tasa_pico y pico sostenido pico_min minutos, con conflictos al azar."""
    with lock:
        if S["corriendo"]: return False
    total = calent_s + rampa_s + int(pico_min * 60)
    if not iniciar(tasa_base, total): return False
    with lock: S.update(modo="rampa", fase="calentamiento", auto_conflictos=True)
    def control():
        t0 = time.time()
        while True:
            with lock:
                if not S["corriendo"]: S.update(modo="normal", fase="", auto_conflictos=False); return
            t = time.time() - t0
            if t < calent_s: fase, rpm = "calentamiento", tasa_base
            elif t < calent_s + rampa_s: fase, rpm = "rampa", tasa_base + (tasa_pico - tasa_base) * (t - calent_s) / rampa_s
            else: fase, rpm = "pico", tasa_pico
            with lock: S["fase"], S["rpm"] = fase, rpm
            time.sleep(1)
    threading.Thread(target=control, daemon=True).start()
    return True

def detener():
    with lock: S["corriendo"] = False; S["auto_conflictos"] = False
    escribir_resumen()

# ---------- conflictos ----------
def bloque_libre():
    with lock:
        for _ in range(200):
            b = rnd.randrange(100001, 130000 - 6, 6)
            if b not in bloques_usados:
                bloques_usados.add(b); return b
    return rnd.randrange(100001, 129990)

def inyectar(n, tipo):
    n = max(2, min(int(n), 50))
    if tipo == "aleatorio": tipo = rnd.choice(["mismo", "cruzados", "vendido"])
    base = bloque_libre(); nota = ""
    grupos = []
    if tipo == "mismo":
        grupos = [[base]] * n
    elif tipo == "cruzados":
        for _ in range(n):
            k = rnd.randint(2, 4); ini = base + rnd.randint(0, 6 - k); grupos.append(list(range(ini, ini + k)))
    else:   # ya vendida
        with lock: vendida = rnd.choice(confirmados) if confirmados else None
        if vendida is None:                                    # no hay ninguna aún: se vende una primero
            c = "pre" + nuevo_id()
            if reservar(c, [base])[0] == "OK": confirmar(c, [base]); vendida = base; nota = "Se vendió antes la silla %d para poder probar." % base
        if vendida is None: return {"error": "no se pudo preparar una silla vendida"}
        grupos = [[vendida]] * n
    barrera = threading.Barrier(n); out = [None] * n
    def lanzar(i):
        c = f"x{nuevo_id()}"
        try: barrera.wait(5)
        except Exception: pass
        res, motivo, ms = reservar(c, grupos[i])
        out[i] = dict(solicitud=c, asientos=grupos[i], resultado=res, motivo=motivo, ms=round(ms, 1))
    t0 = time.time()
    hs = [threading.Thread(target=lanzar, args=(i,)) for i in range(n)]
    [h.start() for h in hs]; [h.join(20) for h in hs]
    out = [o for o in out if o]
    ganadoras = [o for o in out if o["resultado"] == "OK"]
    # D-3: ninguna silla aprobada a dos solicitudes
    cuenta = {}
    for o in ganadoras:
        for a in o["asientos"]: cuenta[a] = cuenta.get(a, 0) + 1
    dobles = [a for a, c in cuenta.items() if c > 1]
    esperado_ok = (len(ganadoras) == 0) if tipo == "vendido" else (len(ganadoras) >= 1 and not dobles)
    ev = dict(hora=datetime.now().strftime("%H:%M:%S"), t=t0, tipo=tipo, n=n, sillas=sorted({a for g in grupos for a in g}),
              confirmadas=len(ganadoras), canceladas=len([o for o in out if o["resultado"] == "NO_DISPONIBLE"]),
              errores=len([o for o in out if o["resultado"] not in ("OK", "NO_DISPONIBLE")]),
              dobles=dobles, cumple=bool(esperado_ok and not dobles), nota=nota, detalle=out)
    with lock: eventos.append(ev)
    if not sesion["dir"]:
        sesion["dir"] = os.path.join(SALIDA_BASE, "sesion-" + datetime.now().strftime("%Y%m%d-%H%M%S")); os.makedirs(sesion["dir"], exist_ok=True)
    with open(os.path.join(sesion["dir"], "conflictos.jsonl"), "a") as f: f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    escribir_resumen()
    return ev

# ---------- métricas ----------
def prom(q):
    try:
        with urllib.request.urlopen(PROM + "/api/v1/query?query=" + urllib.parse.quote(q), timeout=3) as r:
            v = json.loads(r.read())["data"]["result"]
            return float(v[0]["value"][1]) if v else None
    except Exception: return None

def p95_cliente():
    ahora = time.time()
    with lock:
        while lat and ahora - lat[0][0] > 60: lat.popleft()
        xs = sorted(m for _, m in lat)
    return xs[int(0.95 * (len(xs) - 1))] if xs else None

def estado():
    gw = prom('histogram_quantile(0.95, sum(rate(taq_reservar_seconds_bucket[1m])) by (le))')
    gw_ms = gw * 1000 if gw is not None and gw == gw else None
    cl = p95_cliente()
    with lock:
        s = dict(S); ev = list(eventos[-30:]); todos = list(eventos)
    s["tiempo_restante"] = max(0, round(s["fin"] - time.time())) if s["corriendo"] and s["fin"] else None
    s["transcurrido"] = round(time.time() - s["inicio"]) if s["inicio"] and s["corriendo"] else 0
    ref = gw_ms if gw_ms is not None else cl
    lim = 250 if s["modo"] == "rampa" else LIM_ASR_MS
    return dict(s=s, p95_gateway_ms=gw_ms, p95_cliente_ms=cl,
                l1=None if ref is None else ref <= lim,
                d3=all(e["cumple"] for e in todos) if todos else None,
                dobles=sum(len(e["dobles"]) for e in todos), n_conflictos=len(todos),
                eventos=ev[::-1], serie=list(serie)[-300:], carpeta=sesion["dir"], limite=lim, pods=pods_info)

def muestrear():
    while True:
        time.sleep(2)
        if int(time.time()) % 6 < 2: leer_hpas()                       # el estado de los pods se refresca cada ~6 s
        pico = prom("taq_conflicto_pico_misma_silla")
        with lock: rpm_real = S["rpm"] if S["corriendo"] else 0
        serie.append(dict(t=time.time(), p95=p95_cliente(), pico=pico or 0, rpm=rpm_real))

def escribir_resumen():
    if not sesion["dir"]: return
    with lock:
        s = dict(S); ev = list(eventos)
    cl = p95_cliente()
    L = ["# Sesión del panel de control — EXP-1", "",
         f"- Solicitudes de reserva enviadas: **{s['enviadas']}** (aprobadas {s['ok']}, canceladas por silla ocupada {s['canceladas']}, errores técnicos {s['errores']})",
         f"- Compras confirmadas: {s['confirmadas']} · abandonadas: {s['abandonadas']}",
         f"- p95 del cliente (último minuto): {'%.1f ms' % cl if cl is not None else 'n/d'} (ASR L-1 ≤ {LIM_ASR_MS} ms)",
         f"- Conflictos inyectados: **{len(ev)}** · dobles reservas detectadas: **{sum(len(e['dobles']) for e in ev)}** (D-3 exige 0)", "",
         "## Conflictos", "", "| Hora | Tipo | Solicitudes | Sillas | Confirmadas | Canceladas | Cumple D-3 |", "|---|---|---|---|---|---|---|"]
    for e in ev:
        sillas = ", ".join(map(str, e["sillas"][:6])) + ("…" if len(e["sillas"]) > 6 else "")
        L.append(f"| {e['hora']} | {e['tipo']} | {e['n']} | {sillas} | {e['confirmadas']} | {e['canceladas']} | {'✅' if e['cumple'] else '❌'} |")
    open(os.path.join(sesion["dir"], "resumen.md"), "w").write("\n".join(L) + "\n")

# ---------- límite de pods (autoescalador) ----------
HPAS = ("nodo-entrada", "nodo-reserva", "nodo-pasarela")
pods_info = {"hpas": [], "error": None}
def leer_hpas():
    """Réplicas actuales y rango del autoescalador de cada pod (kubectl; en AWS corre dentro del clúster con permisos acotados)."""
    try:
        r = subprocess.run(["kubectl", "-n", "taq", "get", "hpa", "-o", "json"], capture_output=True, text=True, timeout=10)
        d = json.loads(r.stdout or "{}")
        pods_info["hpas"] = [dict(nombre=i["metadata"]["name"], min=i["spec"]["minReplicas"], max=i["spec"]["maxReplicas"],
                                  actual=i.get("status", {}).get("currentReplicas", 0), deseadas=i.get("status", {}).get("desiredReplicas", 0))
                             for i in d.get("items", []) if i["metadata"]["name"] in HPAS]
        pods_info["error"] = None if pods_info["hpas"] else (r.stderr.strip()[:120] or "sin autoescaladores")
    except Exception as e:
        pods_info["error"] = str(e)[:120]

def fijar_limite(maximo, minimo=1):
    """Fuerza el rango de réplicas de los tres pods que escalan. max=min=1 equivale al EXP-1 (una réplica fija)."""
    maximo = max(1, min(int(maximo), 20)); minimo = max(1, min(int(minimo), maximo))
    fallos = []
    for h in HPAS:
        r = subprocess.run(["kubectl", "-n", "taq", "patch", "hpa", h, "--type", "merge",
                            "-p", json.dumps({"spec": {"minReplicas": minimo, "maxReplicas": maximo}})], capture_output=True, text=True, timeout=20)
        if r.returncode: fallos.append(h + ": " + r.stderr.strip()[:80])
        elif maximo == 1:
            subprocess.run(["kubectl", "-n", "taq", "scale", f"deploy/{h}", "--replicas=1"], capture_output=True, text=True, timeout=20)
    leer_hpas()
    return dict(ok=not fallos, error="; ".join(fallos) or None, max=maximo, min=minimo)

def reiniciar_estado():
    cmds = ['kubectl -n taq exec deploy/postgres -- psql -U taq -d taq -qc "TRUNCATE reserva_log RESTART IDENTITY"',
            "kubectl -n taq exec deploy/redis -- sh -c 'redis-cli --scan --pattern \"cola_*\" | xargs -r redis-cli del >/dev/null; true'",
            # Se reinician también el gateway y el nodo de reserva para que sus contadores (solicitudes recibidas, p95) vuelvan a 0.
            "kubectl -n taq rollout restart deploy/bd-bloqueo deploy/nodo-entrada deploy/nodo-reserva",
            "kubectl -n taq rollout status deploy/bd-bloqueo --timeout=120s", "kubectl -n taq rollout status deploy/nodo-entrada --timeout=120s",
            "kubectl -n taq rollout status deploy/nodo-reserva --timeout=120s", "sleep 15"]
    for c in cmds: subprocess.run(c, shell=True, capture_output=True)
    with lock:
        for k in ("enviadas", "ok", "canceladas", "errores", "confirmadas", "abandonadas"): S[k] = 0
        eventos.clear(); confirmados.clear(); bloques_usados.clear(); lat.clear(); sesion["dir"] = None

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, obj, code=200):
        b = json.dumps(obj).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/estado": return self._j(estado())
        b = open(os.path.join(AQUI, "index.html"), "rb").read()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        if self.path == "/api/iniciar": return self._j(dict(ok=iniciar(float(d.get("rpm", 400)), int(d.get("duracion_s", 0)))))
        if self.path == "/api/rpm":
            with lock: S["rpm"] = float(d.get("rpm", 0))
            return self._j(dict(ok=True))
        if self.path == "/api/pods": return self._j(fijar_limite(d.get("max", 5), d.get("min", 1)))
        if self.path == "/api/rampa": return self._j(dict(ok=rampa(float(d.get("pico_min", 15)))))
        if self.path == "/api/detener": detener(); return self._j(dict(ok=True))
        if self.path == "/api/conflicto": return self._j(inyectar(d.get("n", 5), d.get("tipo", "mismo")))
        if self.path == "/api/reiniciar":
            if os.environ.get("TAQ_SIN_KUBECTL"):
                return self._j(dict(ok=False, error="En AWS el estado se reinicia con scripts/reiniciar-estado.sh desde tu equipo."))
            detener(); reiniciar_estado(); return self._j(dict(ok=True))
        self._j(dict(error="ruta"), 404)

if __name__ == "__main__":
    threading.Thread(target=muestrear, daemon=True).start()
    print(f"Panel de control EXP-1 en http://localhost:{PUERTO}")
    ThreadingHTTPServer(("0.0.0.0", PUERTO), H).serve_forever()
