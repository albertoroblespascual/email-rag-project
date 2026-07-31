#!/usr/bin/env bash
# Extrae un archivo PST a estructura de carpetas con .eml usando readpst.
#
# Uso:
#   bash 01_extract_pst.sh /ruta/a/archivo.pst data/eml
#
# Requiere: readpst (paquete 'pst-utils' en apt / 'libpst' en algunas distros)
#   sudo apt install readpst

set -euo pipefail

PST_FILE="${1:?Uso: 01_extract_pst.sh <archivo.pst> <dir_salida>}"
OUT_DIR="${2:?Uso: 01_extract_pst.sh <archivo.pst> <dir_salida>}"

if ! command -v readpst &> /dev/null; then
  echo "ERROR: readpst no está instalado. Ejecuta: sudo apt install readpst" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

echo "Extrayendo $PST_FILE -> $OUT_DIR ..."

# -r  : recursivo, preserva estructura de carpetas
# -e  : una carpeta por email (formato .eml en vez de mbox concatenado)
# -o  : directorio de salida
# -D  : incluye elementos borrados si existen (opcional, coméntalo si no lo quieres)
readpst -r -e -o "$OUT_DIR" "$PST_FILE"

COUNT=$(find "$OUT_DIR" -name "*.eml" | wc -l)
echo "Listo. $COUNT mensajes .eml extraídos en $OUT_DIR"
