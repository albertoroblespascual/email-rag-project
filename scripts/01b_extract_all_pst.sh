#!/usr/bin/env bash
# Procesa TODOS los .pst encontrados en un directorio (por defecto data/raw_pst),
# extrayendo cada uno a su propia subcarpeta dentro de data/eml, para que el
# nombre del PST quede reflejado en el metadato "folder" del paso 2 y no haya
# colisiones si dos PST tienen ambos una carpeta "Inbox" o similar.
#
# Uso:
#   bash scripts/01b_extract_all_pst.sh [dir_pst] [dir_salida]
#   bash scripts/01b_extract_all_pst.sh data/raw_pst data/eml   # valores por defecto

set -euo pipefail

PST_DIR="${1:-data/raw_pst}"
OUT_DIR="${2:-data/eml}"
LOG_FILE="data/processed/extraction_log.tsv"

if ! command -v readpst &> /dev/null; then
  echo "ERROR: readpst no está instalado. Ejecuta: sudo apt install readpst" >&2
  exit 1
fi

mkdir -p "$OUT_DIR" "$(dirname "$LOG_FILE")"

mapfile -t PST_FILES < <(find "$PST_DIR" -maxdepth 1 -type f -iname "*.pst" | sort)

if [ ${#PST_FILES[@]} -eq 0 ]; then
  echo "No se encontraron .pst en $PST_DIR" >&2
  exit 1
fi

echo "Encontrados ${#PST_FILES[@]} archivos PST en $PST_DIR"
echo -e "pst_file\tsize_bytes\tsha256\teml_count\tstatus" > "$LOG_FILE"

for pst in "${PST_FILES[@]}"; do
  base=$(basename "$pst" .pst)
  # sanea el nombre para usarlo como carpeta (espacios, acentos raros, etc.)
  safe_base=$(echo "$base" | tr ' ' '_' | tr -cd '[:alnum:]_-')
  dest="$OUT_DIR/$safe_base"

  echo ""
  echo "=== Procesando: $pst -> $dest ==="

  size=$(stat -c%s "$pst" 2>/dev/null || stat -f%z "$pst")
  echo "  Tamaño: $((size / 1024 / 1024)) MB. Calculando checksum..."
  checksum=$(sha256sum "$pst" | awk '{print $1}')

  mkdir -p "$dest"
  if readpst -r -e -o "$dest" "$pst"; then
    count=$(find "$dest" -name "*.eml" | wc -l)
    echo "  OK: $count mensajes extraídos."
    echo -e "$pst\t$size\t$checksum\t$count\tOK" >> "$LOG_FILE"
  else
    echo "  [ERROR] readpst falló en $pst"
    echo -e "$pst\t$size\t$checksum\t0\tERROR" >> "$LOG_FILE"
  fi
done

echo ""
echo "Extracción completa. Log en $LOG_FILE"
echo "Total .eml generados: $(find "$OUT_DIR" -name "*.eml" | wc -l)"
