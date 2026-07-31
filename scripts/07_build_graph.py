#!/usr/bin/env python3
"""
Fase 2: extrae entidades (personas, clientes, proyectos, tecnologías,
decisiones) de cada correo usando Qwen2.5 (salida JSON estructurada) y
construye un grafo en Neo4j.

Requiere:
    docker run -d -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/tu_password neo4j

Uso:
    python 07_build_graph.py --input data/processed/emails_enriched.jsonl \
        --neo4j-uri bolt://localhost:7687 --neo4j-user neo4j --neo4j-password tu_password
"""
import argparse
import json
from pathlib import Path

import ollama
from neo4j import GraphDatabase
from tqdm import tqdm

LLM_MODEL = "qwen2.5:72b"

EXTRACTION_PROMPT = """Extrae del siguiente correo, en JSON estricto y nada más
(sin explicaciones, sin markdown), las entidades mencionadas:

{{
  "personas": ["nombre completo", ...],
  "clientes": ["nombre de cliente/empresa", ...],
  "proyectos": ["nombre de proyecto/licitación", ...],
  "tecnologias": ["tecnología o producto", ...],
  "decisiones": ["decisión o acuerdo breve, máx 15 palabras", ...]
}}

Correo:
Asunto: {subject}
De: {from_}
Fecha: {date}

{body}
"""


def extract_entities(record: dict) -> dict:
    prompt = EXTRACTION_PROMPT.format(
        subject=record.get("subject", ""),
        from_=record.get("from", ""),
        date=record.get("date", ""),
        body=(record.get("body", "") or "")[:3000],
    )
    resp = ollama.chat(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
    )
    try:
        return json.loads(resp["message"]["content"])
    except Exception:
        return {"personas": [], "clientes": [], "proyectos": [], "tecnologias": [], "decisiones": []}


def write_to_graph(tx, record: dict, entities: dict):
    email_id = record["id"]
    tx.run(
        """
        MERGE (e:Email {id: $id})
        SET e.subject = $subject, e.date = $date, e.folder = $folder, e.thread_id = $thread_id
        MERGE (sender:Persona {email: $from})
        MERGE (sender)-[:ENVIO]->(e)
        """,
        id=email_id,
        subject=record.get("subject", ""),
        date=record.get("date"),
        folder=record.get("folder"),
        thread_id=record.get("thread_id"),
        **{"from": record.get("from", "desconocido")},
    )

    for persona in entities.get("personas", []):
        tx.run(
            "MERGE (p:Persona {nombre: $nombre}) "
            "MERGE (p)-[:MENCIONADO_EN]->(e:Email {id: $id})",
            nombre=persona, id=email_id,
        )
    for cliente in entities.get("clientes", []):
        tx.run(
            "MERGE (c:Cliente {nombre: $nombre}) "
            "MERGE (e:Email {id: $id})-[:RELACIONADO_CON]->(c)",
            nombre=cliente, id=email_id,
        )
    for proyecto in entities.get("proyectos", []):
        tx.run(
            "MERGE (pr:Proyecto {nombre: $nombre}) "
            "MERGE (e:Email {id: $id})-[:PARTE_DE]->(pr)",
            nombre=proyecto, id=email_id,
        )
    for tec in entities.get("tecnologias", []):
        tx.run(
            "MERGE (t:Tecnologia {nombre: $nombre}) "
            "MERGE (e:Email {id: $id})-[:MENCIONA]->(t)",
            nombre=tec, id=email_id,
        )
    for decision in entities.get("decisiones", []):
        tx.run(
            "MERGE (d:Decision {texto: $texto}) "
            "MERGE (e:Email {id: $id})-[:CONTIENE]->(d)",
            texto=decision, id=email_id,
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    ap.add_argument("--neo4j-user", default="neo4j")
    ap.add_argument("--neo4j-password", required=True)
    ap.add_argument("--limit", type=int, default=None, help="Limitar nº de correos (para pruebas)")
    args = ap.parse_args()

    lines = Path(args.input).read_text(encoding="utf-8").splitlines()
    if args.limit:
        lines = lines[: args.limit]

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))

    print(f"Construyendo grafo a partir de {len(lines)} correos...")
    with driver.session() as session:
        for line in tqdm(lines, desc="Extrayendo entidades"):
            record = json.loads(line)
            entities = extract_entities(record)
            session.execute_write(write_to_graph, record, entities)

    driver.close()
    print("Listo. Grafo construido en Neo4j.")
    print('Ejemplo de consulta en Neo4j Browser: '
          'MATCH (p:Persona)-[:MENCIONADO_EN]->(e:Email)-[:RELACIONADO_CON]->(c:Cliente {nombre:"Henry Schein"}) '
          'RETURN p, e, c')


if __name__ == "__main__":
    main()
