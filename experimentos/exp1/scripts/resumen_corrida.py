#!/usr/bin/env python3
"""Arma resumen.md de una corrida a partir de metricas.json, verificacion.json y ejecucion.json."""
import json, sys
from pathlib import Path
run, n = Path(sys.argv[1]), sys.argv[2]
m = json.loads((run / "metricas.json").read_text())
v = json.loads((run / "verificacion.json").read_text())
e = json.loads((run / "ejecucion.json").read_text())
g = m["gateway_ok"]
valida = m["ejecucion_valida"]
carga = (run / "carga-maquina.txt").read_text().strip() if (run / "carga-maquina.txt").exists() else "no registrada"
l1 = g["p95_ms"] <= 150
d3 = (v["asientos_con_mas_de_una_reserva_auditoria"] == 0 and v["asientos_con_mas_de_una_reserva_bitacora"] == 0
      and v["asientos_vendidos_duplicados_bd_reserva"] == 0 and v["asientos_bloqueados_duplicados_bd_reserva"] == 0
      and v["bloqueos_parciales"] == 0 and not v["conflictos_fallidos"] and v["bloqueos_huerfanos_sin_ok_en_cliente"] == 0)
venc = v["revisiones_4min_rechazadas"] == v["revisiones_4min_total"] and v["revisiones_8min_exitosas"] == v["revisiones_8min_total"]
(run / "resumen.md").write_text(f"""# EXP-1 — Corrida {n} (semilla {e['semilla']})

**Validez de la corrida: {'✅ válida' if valida else '⚠️ INVÁLIDA — no usar para concluir'}.** Atraso del generador de carga frente al calendario: p95 = {m['generador']['retraso_p95_ms']:.0f} ms, máx. = {m['generador']['retraso_max_ms']:.0f} ms. Diferencia de solicitudes gateway vs. cliente: {m['diferencia_conteo_gateway_cliente']*100:.2f} %. Carga de la máquina (load average 1 min, antes → después): {carga}.

| ASR | Resultado | Medida |
|---|---|---|
| **L-1** (p95 ≤ 150 ms) | {'✅ cumple' if l1 else '❌ no cumple'} | p95 gateway = **{g['p95_ms']:.1f} ms** · p95 cliente = {m['cliente_ok']['p95_ms']:.1f} ms · {g['fraccion_le_150ms']*100:.2f} % de las reservas ≤ 150 ms |
| **D-3** (0 asientos con más de una reserva) | {'✅ cumple' if d3 else '❌ no cumple'} | {v['asientos_con_mas_de_una_reserva_auditoria']} asientos con doble reserva · {v['bloqueos_parciales']} bloqueos parciales · {v['conflictos_con_resultado_esperado']} de {v['conflictos_total']} conflictos con el resultado esperado |
| Vencimiento a los 8 min | {'✅ cumple' if venc else '❌ no cumple'} | revisión 4 min rechazada {v['revisiones_4min_rechazadas']}/{v['revisiones_4min_total']} · revisión >8 min exitosa {v['revisiones_8min_exitosas']}/{v['revisiones_8min_total']} · liberación real mín/p50/máx = {v['liberacion_min_s']}/{v['liberacion_p50_s']}/{v['liberacion_max_s']} s |

**Carga:** {e['llegadas_normales']} llegadas normales y {e['conflictos']} conflictos programados ({e['calentamiento_s']} s de calentamiento + {e['trafico_s']} s de tráfico). \
Solicitudes de reservar enviadas: {v['solicitudes_reservar_total']}; errores técnicos: {v['errores_tecnicos']}; confirmaciones exitosas: {v['confirmaciones_ok']}/{v['confirmaciones']}.

## Archivos de esta corrida

| Archivo | Contenido |
|---|---|
| [metricas.md](metricas.md) / `metricas.json` | Latencia (gateway y cliente), CPU, memoria, colas, hilo único |
| [verificacion.md](verificacion.md) / `verificacion.json` | Comprobaciones de D-3 y del vencimiento |
| `bitacora.csv` | Cada solicitud enviada: asiento, comprador, resultado y hora |
| `ejecucion.json` | Semilla, marcas de tiempo y tamaño del calendario |
| `jmeter.jtl`, `jmeter.log` | Salida cruda de JMeter |
| `graficas/*.png` | Gráficas de la corrida (p95, colas, hilo único, CPU, memoria) |
| `prometheus/*.json` | Series crudas de Prometheus (paso de 5 s) |
| `tablero-grafana.json` | Tablero de Grafana usado para seguir la corrida |
""")
