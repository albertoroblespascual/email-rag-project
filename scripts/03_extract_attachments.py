#!/usr/bin/env python3
"""
Enriquece emails.jsonl añadiendo el texto extraído de cada adjunto
(PDF, DOCX, PPTX, XLSX, TXT). Usa `unstructured` como motor principal,
con fallback a extractores nativos si `unstructured` falla en un archivo.

Uso:
    python 03_extract_attachments.py --emails data/processed/emails.jsonl \
        --output data/processed/emails_enriched.jsonl
"""
import argparse
import json
from pathlib import Path

from tqdm import tqdm

from _jsonl_utils import read_jsonl_lines

SUPPORTED_EXT = {".pdf", ".docx", ".pptx", ".xlsx", ".txt"}


def extract_with_unstructured(path: Path) -> str:
    from unstructured.partition.auto import partition
    elements = partition(filename=str(path))
    return "\n".join(el.text for el in elements if getattr(el, "text", None))


def extract_fallback(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if ext == ".docx":
            import docx
            doc = docx.Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs)
        if ext == ".pptx":
            from pptx import Presentation
            prs = Presentation(str(path))
            texts = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        texts.append(shape.text_frame.text)
            return "\n".join(texts)
        if ext == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(str(path), data_only=True)
            texts = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    texts.append(" ".join(str(c) for c in row if c is not None))
            return "\n".join(texts)
        if ext == ".txt":
            return path.read_text(errors="replace")
    except Exception as e:
        return f"[ERROR extrayendo {path.name}: {e}]"
    return ""


def extract_attachment_text(path_str: str) -> dict:
    path = Path(path_str)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXT or not path.exists():
        return {"path": path_str, "text": "", "extractor": "skipped"}

    try:
        text = extract_with_unstructured(path)
        extractor = "unstructured"
    except Exception:
        text = extract_fallback(path)
        extractor = "fallback"

    return {"path": path_str, "filename": path.name, "text": text, "extractor": extractor}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emails", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    in_path = Path(args.emails)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = read_jsonl_lines(in_path)
    print(f"Procesando {len(lines)} correos...")

    with out_path.open("w", encoding="utf-8") as out_f:
        for line in tqdm(lines, desc="Extrayendo adjuntos"):
            record = json.loads(line)
            attachment_texts = []
            for att_path in record.get("attachments", []):
                attachment_texts.append(extract_attachment_text(att_path))
            record["attachment_texts"] = attachment_texts
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Listo. -> {out_path}")


if __name__ == "__main__":
    main()
