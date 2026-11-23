#!/usr/bin/env python3
"""EXP-3 / S-2: medida INDEPENDIENTE del tiempo de recuperación (no usa las métricas internas de componente_respuesta_ataque).

Durante la corrida vigila bd_auditoria: cada alerta (fila ATAQUE_DETECTADO) abre un seguimiento de la cuenta. Cada pocos
milisegundos consulta el ESTADO REAL y marca el instante en que se cumplen las tres condiciones:
  1) asientos liberados      -> bd_bloqueo (hilo único): la cuenta retiene 0 asientos
  2) cuenta revocada         -> Redis (cuentas_revocadas) y Postgres (cuenta_revocada)
  3) órdenes canceladas      -> Postgres (orden_cancelada): tantas como asientos retenía la cuenta
El tiempo es: hora de la última consulta que lo confirma MENOS la hora de la evidencia de la alerta. Las dos horas salen de
relojes de los pods (detector, respuesta y bd_bloqueo, sincronizados por NTP del nodo), no del reloj de esta máquina.
Es una cota superior: la consulta puede llegar unos milisegundos después de que el estado cambió.

Uso: medir_recuperacion.py <salida.json> [--deteccion URL] [--respuesta URL] [--bloqueo URL] [--paso-ms 5] [--hasta-epoch S] [--archivo-parar RUTA]
Termina con SIGINT/SIGTERM, al llegar --hasta-epoch o cuando exista --archivo-parar. Escribe el JSON al terminar (y cada 20 s)."""
import argparse, http.client, json, os, signal, sys, time, urllib.parse

ap = argparse.ArgumentParser()
ap.add_argument("salida")
ap.add_argument("--deteccion", default="http://localhost:30091")
ap.add_argument("--respuesta", default="http://localhost:30092")
ap.add_argument("--bloqueo", default="http://localhost:30090")
ap.add_argument("--paso-ms", type=float, default=5.0)
ap.add_argument("--hasta-epoch", type=float, default=0)
ap.add_argument("--archivo-parar", default="")
ap.add_argument("--limite-ms", type=int, default=5000, help="tras este tiempo un seguimiento se da por no completado")
a = ap.parse_args()

class Cliente:
    """HTTP con conexión persistente (menos costo por consulta que abrir una conexión cada vez)."""
    def __init__(self, url):
        u = urllib.parse.urlparse(url); self.host, self.port = u.hostname, u.port or 80; self.c = None
    def get(self, ruta):
        for intento in (0, 1):
            try:
                if self.c is None: self.c = http.client.HTTPConnection(self.host, self.port, timeout=10)
                self.c.request("GET", ruta); r = self.c.getresponse(); cuerpo = r.read()
                if r.status != 200: raise RuntimeError(f"HTTP {r.status} en {ruta}")
                return json.loads(cuerpo)
            except Exception:
                try: self.c.close()
                except Exception: pass
                self.c = None
                if intento: raise
det, res, blo = Cliente(a.deteccion), Cliente(a.respuesta), Cliente(a.bloqueo)

parar = False
def _s(*_):
    global parar; parar = True
signal.signal(signal.SIGINT, _s); signal.signal(signal.SIGTERM, _s)

ultimo_id = 0
seguimientos = {}          # cuenta -> estado del seguimiento
resultados = []
errores = 0
def escribir():
    with open(a.salida, "w") as f:
        json.dump({"paso_ms": a.paso_ms, "mediciones": resultados, "sin_completar": [
            {"cuenta": c, "t_alerta_ms": s["t_alerta"], "retenidos_max": s["n0"], "estado": s["ult"]} for c, s in seguimientos.items()],
            "errores_de_consulta": errores}, f, indent=1)

def cerrar(c, s, t_fin, completo):
    resultados.append({"cuenta": c, "t_alerta_ms": s["t_alerta"], "t_fin_ms": t_fin, "recuperacion_ms": (t_fin - s["t_alerta"]) if completo else None,
                       "completo": completo, "asientos_retenidos_vistos": s["n0"], "ordenes_esperadas": s["n0"],
                       "n0_inferido": bool(s.get("inferido")), "t_liberado_ms": s.get("t_lib"), "t_revocada_ms": s.get("t_rev"), "t_ordenes_ms": s.get("t_ord")})

t_json = time.time()
while not parar:
    ahora = time.time()
    if a.hasta_epoch and ahora > a.hasta_epoch: break
    if a.archivo_parar and os.path.exists(a.archivo_parar): break
    try:
        # 1) alertas nuevas (evidencia de detección)
        filas = det.get(f"/deteccion/auditoria?desde={ultimo_id}&tipo=ATAQUE_DETECTADO&limite=500")
        for f in filas:
            ultimo_id = max(ultimo_id, f["id"])
            seguimientos[f["cuenta"]] = {"t_alerta": f["ts_evidencia"], "n0": 0, "ult": None}
        # 2) estado real de las cuentas en seguimiento
        if seguimientos:
            cuentas = ",".join(list(seguimientos)[:200])
            b = blo.get("/bloqueo/retenidos?compradores=" + urllib.parse.quote(cuentas, safe=","))
            r = res.get("/respuesta/estado?cuentas=" + urllib.parse.quote(cuentas, safe=","))
            t_srv = max(b["ahora"], r["ahora_ms"])
            for c in list(seguimientos)[:200]:
                s = seguimientos[c]; ret = b["retenidos"].get(c, 0); e = r["cuentas"].get(c, {})
                s["n0"] = max(s["n0"], ret)
                if s["n0"] == 0 and ret == 0 and e.get("ordenes_canceladas", 0) > 0:   # la recuperación terminó antes de la primera consulta
                    s["n0"] = e["ordenes_canceladas"]; s["inferido"] = True
                s["ult"] = {"retenidos": ret, **e}
                if ret == 0 and s["n0"] > 0 and "t_lib" not in s: s["t_lib"] = b["ahora"]
                if e.get("revocada_redis") and e.get("revocada_postgres") and "t_rev" not in s: s["t_rev"] = r["ahora_ms"]
                ordenes_ok = e.get("ordenes_canceladas", 0) >= s["n0"] and s["n0"] > 0
                if ordenes_ok and "t_ord" not in s: s["t_ord"] = r["ahora_ms"]
                if "t_lib" in s and "t_rev" in s and "t_ord" in s:
                    cerrar(c, s, max(s["t_lib"], s["t_rev"], s["t_ord"]), True); del seguimientos[c]
                elif t_srv - s["t_alerta"] > a.limite_ms:
                    cerrar(c, s, t_srv, False); del seguimientos[c]
    except Exception as ex:
        errores += 1
        print("aviso: consulta fallida:", ex, file=sys.stderr)
        time.sleep(0.5)
    if time.time() - t_json > 20: escribir(); t_json = time.time()
    time.sleep(a.paso_ms / 1000.0)
# último barrido antes de salir: lo pendiente se cierra como no completado
escribir()
print(f"seguimientos completos: {sum(1 for m in resultados if m['completo'])}, no completos: {sum(1 for m in resultados if not m['completo']) + len(seguimientos)}", file=sys.stderr)
