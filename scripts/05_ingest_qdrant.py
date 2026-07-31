#!/usr/bin/env python3
"""
Ingresa los chunks con embeddings en una colección de Qdrant, con
metadatos indexados para permitir filtrado combinado
(semántico + from/to/folder/date/thread).

Requiere Qdrant corriendo (docker run ... qdrant/qdrant), por defecto en
localhost:6333.

Uso:
    python 05_ingest_qdrant.py --input data/processed/chunks_with_embeddings.jsonl \
        --collection correos_alberto
"""
import argparse
import json
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    PayloadSchemaType,
)
from tqdm import tqdm

from _jsonl_utils import read_jsonl_lines

BATCH_SIZE = 128
VECTOR_SIZE = 1024  # dimensión de BGE-M3


def ensure_collection(client: QdrantClient, name: str):
    existing = [c.name for c in client.get_collections().collections]
    if name in existing:
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    # índices de payload para filtrado rápido por metadatos
    for field, schema in [
        ("from", PayloadSchemaType.KEYWORD),
        ("to", PayloadSchemaType.KEYWORD),
        ("folder", PayloadSchemaType.KEYWORD),
        ("thread_id", PayloadSchemaType.KEYWORD),
        ("date", PayloadSchemaType.DATETIME),
        ("content_type", PayloadSchemaType.KEYWORD),
    ]:
        try:
            client.create_payload_index(collection_name=name, field_name=field, field_schema=schema)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--collection", required=True)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=6333)
    args = ap.parse_args()

    client = QdrantClient(host=args.host, port=args.port)
    ensure_collection(client, args.collection)

    lines = read_jsonl_lines(args.input)
    print(f"Indexando {len(lines)} chunks en Qdrant (colección: {args.collection})...")

    batch = []
    for line in tqdm(lines, desc="Ingestando"):
        rec = json.loads(line)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, rec["chunk_id"]))
        payload = {k: v for k, v in rec.items() if k != "embedding"}
        batch.append(PointStruct(id=point_id, vector=rec["embedding"], payload=payload))

        if len(batch) >= BATCH_SIZE:
            client.upsert(collection_name=args.collection, points=batch)
            batch = []

    if batch:
        client.upsert(collection_name=args.collection, points=batch)

    count = client.count(collection_name=args.collection).count
    print(f"Listo. Colección '{args.collection}' contiene {count} puntos.")


if __name__ == "__main__":
    main()
