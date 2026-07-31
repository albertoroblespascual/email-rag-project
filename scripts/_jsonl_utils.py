"""
Utilidades compartidas del pipeline.

read_jsonl_lines: lee un archivo JSONL devolviendo la lista de líneas de
texto crudo, una por registro. Usa SIEMPRE esto (o el mismo patrón) en vez
de `texto.splitlines()` para leer JSONL: `str.splitlines()` en Python trata
como salto de línea no solo '\n', sino también varios separadores Unicode
(\u2028 LINE SEPARATOR, \u2029 PARAGRAPH SEPARATOR, \x0b, \x0c, \x1c-\x1e,
\x85...). Si el CUERPO de un correo contiene alguno de esos caracteres
(ocurre con contenido copiado de páginas web, ciertos PDFs, o firmas HTML
mal codificadas), `json.dumps` no lo escapa por no ser un carácter de
control ASCII — queda literal dentro del string JSON — y `splitlines()`
entonces corta ese registro en dos líneas rotas, rompiendo el parseo JSON
más adelante. `str.split("\n")` solo corta por el byte real de salto de
línea, que es el único delimitador válido en JSONL.
"""
from pathlib import Path


def read_jsonl_lines(path) -> list:
    text = Path(path).read_text(encoding="utf-8")
    return [line for line in text.split("\n") if line.strip()]
