#!/usr/bin/env python3
"""Une métricas y verificación de una ejecución de EXP-2 en resumen.md. Uso: resumen_exp2.py <carpeta> <n> <entorno>"""
import json, pathlib, sys
c = pathlib.Path(sys.argv[1]); n = sys.argv[2]; ent = sys.argv[3] if len(sys.argv) > 3 else ""
M = json.loads((c / "metricas.json").read_text())
try: V = json.loads((c / "verificacion.json").read_text())
except Exception: V = None
d3 = V is not None and all(V[k] == 0 for k in ("asientos_con_mas_de_una_reserva_auditoria", "asientos_con_mas_de_una_reserva_bitacora",
        "asientos_vendidos_duplicados_bd_reserva", "bloqueos_parciales")) and V["conflictos_con_resultado_esperado"] == V["conflictos_total"]
f = lambda v: "n/d" if v is None else f"{v:.1f}"
rep = ", ".join(f"{d} → {v['final']} (máx. {v['maximo']})" for d, v in sorted(M["replicas"].items()))
L = [f"# EXP-2 — Ejecución {n}" + (f" ({ent})" if ent else ""), "",
     f"**Validez: {'✅ válida' if M['valida'] else '⚠️ NO válida (el generador de carga se atrasó; no usar para concluir)'}.** Atraso del generador p95 = {M['cliente']['retraso_generador_p95_ms']} ms.", "",
     "| ASR | Resultado | Medida |", "|---|---|---|",
     f"| **E-1** (p95 < 250 ms en el pico, sin perder solicitudes) | {'✅ cumple' if M['asr_e1_cumple'] else '❌ no cumple'} | p95 pico = **{f(M['p95_pico_completo_ms'])} ms** (tras equilibrio {f(M['p95_tras_equilibrio_ms'])} ms) · cliente {M['cliente']['p95_pico_ms']} ms · {f(M['solicitudes_por_min_en_pico'])} solicitudes/min · rechazos por cola llena {M['rechazos_cola_llena_total']} · errores técnicos {M['errores_tecnicos']} |",
     f"| **Equilibrio** | ver réplicas | {rep}; réplicas estables desde el segundo {M['equilibrio_desde_s']} |",
     f"| **Hilo único** | {'sin cuello de botella' if M['hilo_unico']['ocupado_pct_max'] < 80 and M['hilo_unico']['cola_operacion_max'] < 50 else 'revisar'} | máx. {f(M['hilo_unico']['ops_s_max'])} ops/s · ocupado máx. {f(M['hilo_unico']['ocupado_pct_max'])} % · cola máx. {M['hilo_unico']['cola_operacion_max']} |"]
if V:
    L.append(f"| **D-3** (0 dobles reservas, todo o nada) | {'✅ cumple' if d3 else '❌ no cumple'} | dobles {V['asientos_con_mas_de_una_reserva_auditoria']} · parciales {V['bloqueos_parciales']} · conflictos con resultado esperado {V['conflictos_con_resultado_esperado']}/{V['conflictos_total']} · 4 min rechazadas {V['revisiones_4min_rechazadas']}/{V['revisiones_4min_total']} · 8 min exitosas {V['revisiones_8min_exitosas']}/{V['revisiones_8min_total']} |")
else:
    L.append("| **D-3** | sin verificación | no se pudo leer `verificacion.json` |")
L += ["", "Detalle: [metricas.md](metricas.md) · [verificacion.md](verificacion.md) · `bitacora.csv` · `prometheus/*.json` · `tablero-grafana.json`."]
(c / "resumen.md").write_text("\n".join(L) + "\n")
print("\n".join(L))
