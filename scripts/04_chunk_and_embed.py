#!/usr/bin/env python3
"""
Divide cada correo (+ texto de adjuntos) en chunks y genera embeddings
con BGE-M3 servido localmente vía Ollama.

Requiere:
    ollama pull bge-m3
    (el servicio ollama debe estar corriendo en localhost:11434)

Uso:
    python 04_chunk_and_embed.py --input data/processed/emails_enriched.jsonl \
        --output data/processed/chunks_with_embeddings.jsonl
"""
import argparse
import json
from pathlib import Path

import ollama
from tqdm import tqdm

CHUNK_SIZE = 800       # caracteres aprox. por chunk (ajustable)
CHUNK_OVERLAP = 150
EMBED_MODEL = "bge-m3"


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return chunks


def build_source_text(record: dict) -> list:
    """Devuelve lista de (texto, tipo, origen) a trocear: cuerpo + adjuntos."""
    sources = []
    body = record.get("body", "")
    if body:
        sources.append((body, "body", None))
    for att in record.get("attachment_texts", []):
        if att.get("text"):
            sources.append((att["text"], "attachment", att.get("filename")))
    return sources


def embed(text: str) -> list:
    resp = ollama.embeddings(model=EMBED_MODEL, prompt=text)
    return resp["embedding"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = in_path.read_text(encoding="utf-8").splitlines()
    print(f"Chunking + embeddings para {len(lines)} correos (modelo: {EMBED_MODEL})...")

    n_chunks = 0
    with out_path.open("w", encoding="utf-8") as out_f:
        for line in tqdm(lines, desc="Emails"):
            record = json.loads(line)
            base_meta = {
                "email_id": record["id"],
                "subject": record.get("subject", ""),
                "from": record.get("from", ""),
                "to": record.get("to", []),
                "cc": record.get("cc", []),
                "date": record.get("date"),
                "folder": record.get("folder"),
                "thread_id": record.get("thread_id"),
            }

            for text, kind, origin in build_source_text(record):
                for i, chunk in enumerate(chunk_text(text)):
                    try:
                        vector = embed(chunk)
                    except Exception as e:
                        print(f"  [WARN] embedding falló en {record['id']} chunk {i}: {e}")
                        continue
                    out_record = {
                        **base_meta,
                        "chunk_id": f"{record['id']}_{kind}_{origin or ''}_{i}",
                        "chunk_index": i,
                        "content_type": kind,          # "body" | "attachment"
                        "attachment_filename": origin,
                        "text": chunk,
                        "embedding": vector,
                    }
                    out_f.write(json.dumps(out_record, ensure_ascii=False) + "\n")
                    n_chunks += 1

    print(f"Listo. {n_chunks} chunks generados. -> {out_path}")


if __name__ == "__main__":
    main()
