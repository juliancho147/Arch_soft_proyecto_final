# Intentos descartados de EXP-2

## intento1-corrida-1 (local, 2026-11-19)
Inválido. Los pods `nodo-entrada` (límite de memoria 384 MiB) y `bd-bloqueo` (384 MiB, heap 256 MB) fueron terminados por falta de memoria (OOMKilled) durante el pico.
`bd-bloqueo` se reinició y perdió su estado en memoria, por eso el verificador de D-3 reporta bloqueos parciales y conflictos "sin resultado esperado": es un fallo de la configuración de memoria del ensayo local, no una conclusión sobre el diseño.
El generador de carga se atrasó (p95 = 125 s) y el 70 % de las solicitudes dieron error. El nodo de Docker llegó a 5,4 GiB, así que el límite fue el de cada pod, no el del nodo.
