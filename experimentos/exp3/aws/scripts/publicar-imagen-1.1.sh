#!/usr/bin/env bash
# Conservado por compatibilidad: publica la etiqueta 1.1 (sin tipos de ataque). Para la actual use publicar-imagen.sh (TAG=1.2 por defecto).
TAG=1.1 exec "$(dirname "$0")/publicar-imagen.sh"
