# Resultados de EXP-3

| Carpeta | Qué es | ¿Oficial? |
|---|---|---|
| `ensayo-humo-1-medida-desde-mac` | Prueba de humo con la medida independiente de S-2 corriendo desde el Mac (medía la red, no el sistema) | No |
| `ensayo-humo-2-medida-en-cluster` | Prueba de humo, solo ataques de bot individual, medida independiente dentro del clúster (imagen 1.1) | No |
| `ensayo-humo-3-granja-no-detectada` | Primera prueba con los tres tipos de ataque: la granja no se detectó porque Kubernetes ocultaba el encabezado `X-Forwarded-For` | No |
| `ensayo-humo-4-algoritmo-v1` | Tres tipos de ataque con el algoritmo original de marca en bloque (secuencial, imagen 1.2). **Línea base "antes"**: la granja de 30 cuentas incumple S-1 (p95 de detección 182 ms) y se acerca al límite de S-2 (234 ms) | No: ensayo de humo |
| `corrida-N` | Ejecuciones oficiales, con el algoritmo v2 (evidencia y recuperación en lote, imagen 1.3) | Sí |

Los ensayos de humo son versiones cortas (5 ataques, 20 a 30 cuentas, pico de 2.000 por minuto) y no son evidencia de los ASR.
