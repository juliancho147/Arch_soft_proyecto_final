#!/usr/bin/env python3
"""Consolida las corridas de EXP-1 en resultados/resumen-exp1.md y resultados/resumen-exp1.json."""
import json, statistics
from pathlib import Path

res = Path(__file__).resolve().parent.parent / "resultados"
corridas = []
for d in sorted(res.glob("corrida-*")):
    if not (d / "verificacion.json").exists(): continue
    m, v, e = (json.loads((d / f).read_text()) for f in ("metricas.json", "verificacion.json", "ejecucion.json"))
    d3 = (v["asientos_con_mas_de_una_reserva_auditoria"] == 0 and v["asientos_con_mas_de_una_reserva_bitacora"] == 0
          and v["asientos_vendidos_duplicados_bd_reserva"] == 0 and v["asientos_bloqueados_duplicados_bd_reserva"] == 0
          and v["bloqueos_parciales"] == 0 and not v["conflictos_fallidos"] and v["bloqueos_huerfanos_sin_ok_en_cliente"] == 0)
    venc = (v["revisiones_4min_rechazadas"] == v["revisiones_4min_total"]
            and v["revisiones_8min_exitosas"] == v["revisiones_8min_total"])
    corridas.append(dict(
        corrida=d.name, semilla=e["semilla"], llegadas=e["llegadas_normales"], conflictos=v["conflictos_total"],
        solicitudes=v["solicitudes_reservar_total"], tasa_por_min=round(m["tasa_real_reservar_por_min"]),
        p95_gateway_ms=m["gateway_ok"]["p95_ms"], p95_cliente_ms=m["cliente_ok"]["p95_ms"],
        p50_gateway_ms=m["gateway_ok"]["p50_ms"], p99_gateway_ms=m["gateway_ok"]["p99_ms"],
        pct_le_150=m["gateway_ok"]["fraccion_le_150ms"] * 100,
        valida=m["ejecucion_valida"], atraso_p95_ms=m["generador"]["retraso_p95_ms"], l1=m["gateway_ok"]["p95_ms"] <= 150, d3=d3, vencimiento=venc,
        doble_reserva=v["asientos_con_mas_de_una_reserva_auditoria"], parciales=v["bloqueos_parciales"],
        conflictos_ok=v["conflictos_con_resultado_esperado"], errores=v["errores_tecnicos"],
        liberacion_p50_s=v["liberacion_p50_s"], liberacion_max_s=v["liberacion_max_s"],
        hilo_unico_pct_max=(m["prometheus"]["hilo_unico_pct"] or {}).get("max"),
        hilo_unico_pct_prom=(m["prometheus"]["hilo_unico_pct"] or {}).get("prom"),
        ops_por_s_prom=(m["prometheus"]["ops_hilo_unico"] or {}).get("prom"),
        cola_solicitud_max=(m["prometheus"]["cola_solicitud"] or {}).get("max"),
        cola_operacion_max=(m["prometheus"]["cola_operacion"] or {}).get("max"),
        cpu_pct_max=max(x["max"] for x in m["prometheus"]["cpu_pct"].values()),
        tasa_hit_cache=m["prometheus"]["cache"]["tasa_hit"] * 100))

if not corridas: raise SystemExit("no hay corridas")
tick = lambda b: "✅" if b else "❌"
f1 = lambda x: "—" if x is None else f"{x:.1f}"
todo_l1, todo_d3, todo_v = (all(c[k] for c in corridas) for k in ("l1", "d3", "vencimiento"))
todas_validas = all(c['valida'] for c in corridas)
md = f"""# EXP-1 — Resultados consolidados

**Hipótesis:** con la carga normal de reservas y una sola réplica, reservar cumple el tiempo de respuesta definido (L-1: p95 ≤ 150 ms) y, aun con conflictos inyectados al azar, solo una solicitud obtiene cada asiento, sin bloqueos parciales ni asientos con más de una reserva (D-3).

## Veredicto

{'' if todas_validas else '> ⚠️ **Hay corridas inválidas** (el generador de carga se atrasó o gateway y cliente no vieron lo mismo). El veredicto no es concluyente hasta repetirlas.'}

| ASR | Corridas que cumplen | Veredicto |
|---|---|---|
| L-1 — p95 de reservar ≤ 150 ms | {sum(c['l1'] for c in corridas)} de {len(corridas)} | {tick(todo_l1)} {'Cumple' if todo_l1 else 'No cumple en todas las corridas'} |
| D-3 — 0 asientos con más de una reserva | {sum(c['d3'] for c in corridas)} de {len(corridas)} | {tick(todo_d3)} {'Cumple' if todo_d3 else 'No cumple en todas las corridas'} |
| Vencimiento a los 8 min | {sum(c['vencimiento'] for c in corridas)} de {len(corridas)} | {tick(todo_v)} {'Cumple' if todo_v else 'No cumple en todas las corridas'} |

## Por corrida

| Corrida | Válida | Atraso gen. p95 (ms) | Semilla | Llegadas | Conflictos | Solicitudes de reservar | p50 gw (ms) | p95 gw (ms) | p99 gw (ms) | p95 cliente (ms) | % ≤ 150 ms | L-1 | D-3 | Vencimiento |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
""" + "\n".join(
    f"| {c['corrida']} | {tick(c['valida'])} | {c['atraso_p95_ms']:.0f} | {c['semilla']} | {c['llegadas']} | {c['conflictos']} | {c['solicitudes']} | {f1(c['p50_gateway_ms'])} | **{f1(c['p95_gateway_ms'])}** | {f1(c['p99_gateway_ms'])} | {f1(c['p95_cliente_ms'])} | {c['pct_le_150']:.2f} | {tick(c['l1'])} | {tick(c['d3'])} | {tick(c['vencimiento'])} |" for c in corridas) + f"""

**p95 del gateway** (la medida del ASR): promedio de las corridas = {statistics.mean(c['p95_gateway_ms'] for c in corridas):.1f} ms, peor = {max(c['p95_gateway_ms'] for c in corridas):.1f} ms. \
Diferencia con el cliente: {statistics.mean(c['p95_cliente_ms'] - c['p95_gateway_ms'] for c in corridas):.1f} ms de promedio.

## D-3 y vencimiento

| Corrida | Asientos con doble reserva | Bloqueos parciales | Conflictos con resultado esperado | Liberación real p50 / máx (s) | Errores técnicos |
|---|---|---|---|---|---|
""" + "\n".join(
    f"| {c['corrida']} | {c['doble_reserva']} | {c['parciales']} | {c['conflictos_ok']} de {c['conflictos']} | {f1(c['liberacion_p50_s'])} / {f1(c['liberacion_max_s'])} | {c['errores']} |" for c in corridas) + """

## Recursos y colas (ventana de tráfico normal)

| Corrida | Hilo único: ocupación prom. / máx. (%) | Operaciones/s en `bd_bloqueo` (prom.) | `cola_solicitud` máx. | `cola_operacion` máx. | CPU máx. de un componente (%) | Caché: tasa de acierto (%) |
|---|---|---|---|---|---|---|
""" + "\n".join(
    f"| {c['corrida']} | {f1(c['hilo_unico_pct_prom'])} / {f1(c['hilo_unico_pct_max'])} | {f1(c['ops_por_s_prom'])} | {f1(c['cola_solicitud_max'])} | {f1(c['cola_operacion_max'])} | {f1(c['cpu_pct_max'])} | {f1(c['tasa_hit_cache'])} |" for c in corridas) + """

Detalle de cada corrida: `corrida-N/resumen.md`. Entorno y límites de recursos: [entorno.md](entorno.md).
"""
(res / "resumen-exp1.md").write_text(md)
(res / "resumen-exp1.json").write_text(json.dumps({"experimento": "EXP-1", "asrs": ["L-1", "D-3"],
    "veredicto": {"L-1": todo_l1, "D-3": todo_d3, "vencimiento": todo_v}, "corridas": corridas}, indent=2))
print(md)
