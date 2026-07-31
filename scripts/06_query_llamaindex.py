#!/usr/bin/env python3
"""
Motor de consulta: conecta LlamaIndex a la colección de Qdrant existente
y responde preguntas usando Qwen2.5 (vía Ollama) con citación de fuentes
(correo origen, remitente, fecha, carpeta).

Uso:
    python 06_query_llamaindex.py --collection correos_alberto \
        --query "¿Qué se acordó con Henry Schein sobre MCP?"

    python 06_query_llamaindex.py --collection correos_alberto --interactive
"""
import argparse

from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.vector_stores.types import MetadataFilters, MetadataFilter
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

EMBED_MODEL = "bge-m3"
LLM_MODEL = "qwen2.5:72b"

SYSTEM_PROMPT = (
    "Eres el asistente personal de Alberto para consultar su histórico de "
    "correo corporativo (CORUS Systems). Responde en español, de forma "
    "precisa, citando siempre remitente y fecha de los correos en los que "
    "te bases. Si la información no aparece en el contexto recuperado, "
    "dilo explícitamente en vez de inventar."
)


def build_query_engine(collection: str, host: str, port: int, top_k: int, filters: dict | None):
    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL)
    Settings.llm = Ollama(model=LLM_MODEL, request_timeout=300.0, system_prompt=SYSTEM_PROMPT)

    client = QdrantClient(host=host, port=port)
    vector_store = QdrantVectorStore(client=client, collection_name=collection)
    index = VectorStoreIndex.from_vector_store(vector_store)

    metadata_filters = None
    if filters:
        metadata_filters = MetadataFilters(
            filters=[MetadataFilter(key=k, value=v) for k, v in filters.items()]
        )

    return index.as_query_engine(similarity_top_k=top_k, filters=metadata_filters)


def print_response(response):
    print("\n" + "=" * 70)
    print(response.response)
    print("=" * 70)
    print("Fuentes:")
    for node in response.source_nodes:
        meta = node.node.metadata
        print(
            f"  - [{meta.get('date', '?')}] {meta.get('from', '?')} "
            f"| carpeta: {meta.get('folder', '?')} | asunto: {meta.get('subject', '?')} "
            f"(score={node.score:.3f})"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=6333)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--query", help="Pregunta única (modo no interactivo)")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--from-filter", help="Filtra por remitente exacto (campo 'from')")
    ap.add_argument("--folder-filter", help="Filtra por carpeta del PST")
    args = ap.parse_args()

    filters = {}
    if args.from_filter:
        filters["from"] = args.from_filter
    if args.folder_filter:
        filters["folder"] = args.folder_filter

    engine = build_query_engine(args.collection, args.host, args.port, args.top_k, filters or None)

    if args.interactive:
        print("Modo interactivo. Ctrl+C para salir.")
        while True:
            try:
                q = input("\n> ")
            except (EOFError, KeyboardInterrupt):
                break
            if not q.strip():
                continue
            print_response(engine.query(q))
    elif args.query:
        print_response(engine.query(args.query))
    else:
        ap.error("Especifica --query o --interactive")


if __name__ == "__main__":
    main()
