#!/usr/bin/env python3
"""
Convierte una carpeta de archivos .eml (generados por readpst) en un
único JSONL con metadatos normalizados, y vuelca los adjuntos a disco.

Uso:
    python 02_eml_to_json.py --input data/eml --output data/processed/emails.jsonl \
        --attachments-dir data/attachments
"""
import argparse
import email
import hashlib
import json
import re
from email.header import decode_header
from email.utils import parseaddr, getaddresses, parsedate_to_datetime
from pathlib import Path

from bs4 import BeautifulSoup
from tqdm import tqdm

# Carpetas de PST que NO son correo (calendario, contactos, cachés internas
# de Outlook) y que conviene excluir del corpus de RAG por defecto: su
# estructura no es la de un email y solo añaden ruido a la búsqueda
# semántica. Se filtra por coincidencia de subcadena, insensible a mayúsculas,
# contra el nombre de carpeta relativo (p.ej. ".../Calendario" o ".../Contactos").
DEFAULT_EXCLUDE_FOLDERS = ["Calendario", "Contactos", "Recipient-Cache"]


def decode_mime_header(value: str) -> str:
    """Decodifica cabeceras tipo '=?utf-8?B?...?=' (encoded-words RFC 2047),
    habituales en subject/from cuando contienen acentos o caracteres no-ASCII."""
    if not value:
        return ""
    try:
        parts = decode_header(value)
        decoded = []
        for text, charset in parts:
            if isinstance(text, bytes):
                decoded.append(text.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(text)
        return "".join(decoded).strip()
    except Exception:
        return value


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def get_body(msg: email.message.Message) -> str:
    """Prioriza text/plain; si solo hay HTML, lo limpia."""
    plain, html = None, None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/plain" and plain is None:
                plain = text
            elif ctype == "text/html" and html is None:
                html = text
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace") if payload else ""
            if msg.get_content_type() == "text/html":
                html = text
            else:
                plain = text
        except Exception:
            plain = ""

    if plain:
        return plain.strip()
    if html:
        return clean_html(html)
    return ""


def extract_attachments(msg: email.message.Message, out_dir: Path, email_id: str) -> list:
    saved = []
    if not msg.is_multipart():
        return saved
    for part in msg.walk():
        disp = str(part.get("Content-Disposition") or "")
        filename = part.get_filename()
        if not filename or "attachment" not in disp and part.get_content_maintype() == "multipart":
            continue
        if not filename:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        safe_name = re.sub(r"[^\w\.\-]", "_", filename)
        out_path = out_dir / f"{email_id}__{safe_name}"
        out_path.write_bytes(payload)
        saved.append(str(out_path))
    return saved


def parse_eml_file(path: Path, attachments_dir: Path, folder_name: str) -> dict:
    raw = path.read_bytes()
    msg = email.message_from_bytes(raw)

    email_id = hashlib.sha1(raw).hexdigest()[:16]

    date_hdr = msg.get("Date")
    try:
        date_iso = parsedate_to_datetime(date_hdr).isoformat() if date_hdr else None
    except Exception:
        date_iso = None

    from_name, from_addr = parseaddr(msg.get("From", ""))
    from_name = decode_mime_header(from_name)
    to_list = [addr for _, addr in getaddresses([msg.get("To", "")]) if addr]
    cc_list = [addr for _, addr in getaddresses([msg.get("Cc", "")]) if addr]

    thread_id = msg.get("Thread-Index") or msg.get("References") or msg.get("In-Reply-To") or email_id

    attachments = extract_attachments(msg, attachments_dir, email_id)

    return {
        "id": email_id,
        "subject": decode_mime_header(msg.get("Subject", "")),
        "from": from_addr or from_name,
        "to": to_list,
        "cc": cc_list,
        "date": date_iso,
        "folder": folder_name,
        "thread_id": thread_id,
        "body": get_body(msg),
        "attachments": attachments,
        "source_file": str(path),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Directorio raíz con .eml (salida de readpst)")
    ap.add_argument("--output", required=True, help="Archivo JSONL de salida")
    ap.add_argument("--attachments-dir", required=True, help="Directorio donde volcar adjuntos")
    ap.add_argument(
        "--exclude-folders",
        default=",".join(DEFAULT_EXCLUDE_FOLDERS),
        help=(
            "Lista separada por comas de subcadenas de carpeta a excluir "
            f"(por defecto: {','.join(DEFAULT_EXCLUDE_FOLDERS)}). "
            "Usa '' (vacío) para no excluir nada."
        ),
    )
    args = ap.parse_args()

    exclude_terms = [t.strip().lower() for t in args.exclude_folders.split(",") if t.strip()]

    in_dir = Path(args.input)
    out_path = Path(args.output)
    att_dir = Path(args.attachments_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    att_dir.mkdir(parents=True, exist_ok=True)

    all_eml_files = list(in_dir.rglob("*.eml"))
    if exclude_terms:
        eml_files = [
            p for p in all_eml_files
            if not any(term in str(p.relative_to(in_dir)).lower() for term in exclude_terms)
        ]
        n_excluded = len(all_eml_files) - len(eml_files)
        print(f"Encontrados {len(all_eml_files)} archivos .eml, excluidos {n_excluded} por carpeta ({exclude_terms})")
    else:
        eml_files = all_eml_files
        print(f"Encontrados {len(eml_files)} archivos .eml (sin exclusión de carpetas)")

    n_ok, n_err = 0, 0
    with out_path.open("w", encoding="utf-8") as out_f:
        for path in tqdm(eml_files, desc="Parseando"):
            folder_name = str(path.parent.relative_to(in_dir))
            try:
                record = parse_eml_file(path, att_dir, folder_name)
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                n_ok += 1
            except Exception as e:
                n_err += 1
                print(f"  [WARN] fallo en {path}: {e}")

    print(f"Listo. {n_ok} correos parseados, {n_err} con error. -> {out_path}")


if __name__ == "__main__":
    main()
