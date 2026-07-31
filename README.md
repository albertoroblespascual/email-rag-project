# Email RAG Pipeline — Alberto (ThinkStation PGX)

Pipeline local para convertir tu histórico de PST de Outlook en un sistema
consultable (RAG + grafo de conocimiento), corriendo 100% en tu GB10 con
Ollama + Qdrant + LlamaIndex.

## Arquitectura

```
PST ─▶ readpst ─▶ EML ─▶ parser ─▶ JSON normalizado + adjuntos extraídos
                                        │
                                        ▼
                              chunking + embeddings (BGE-M3 vía Ollama)
                                        │
                                        ▼
                                     Qdrant
                                        │
                                        ▼
                              LlamaIndex QueryEngine ─▶ Qwen2.5:72b
```

## 0. Requisitos previos en el ThinkStation

```bash
sudo apt install readpst           # extracción de PST
ollama pull bge-m3                 # embeddings multilingües
ollama pull qwen2.5:72b            # ya lo tienes según tu setup actual
docker run -d -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/data/qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

### Entorno Python con `uv`

Si no tienes `uv` instalado:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Crear el entorno e instalar dependencias (usa `pyproject.toml`, resuelve en
segundos gracias al resolutor en Rust):

```bash
uv sync
```

Esto crea `.venv/` automáticamente y genera/actualiza `uv.lock` con
versiones fijadas, para reproducibilidad. A partir de aquí, todos los
comandos de este README que empiezan por `python scripts/...` se ejecutan
anteponiendo `uv run`, por ejemplo:

```bash
uv run python scripts/02_eml_to_json.py --input data/eml --output data/processed/emails.jsonl --attachments-dir data/attachments
```

`uv run` usa automáticamente el `.venv` del proyecto sin necesidad de
activarlo manualmente. Si prefieres activarlo tú (por ejemplo para usar
JupyterLab como ya haces en tu stack actual):

```bash
source .venv/bin/activate
```

Para añadir una dependencia nueva más adelante (en vez de editar
`pyproject.toml` a mano):

```bash
uv add nombre-paquete
```

<details>
<summary>Alternativa con pip clásico (si prefieres no usar uv)</summary>

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```
</details>

## Flujo rápido: tengo varios PST y quiero lanzar todo

```bash
# 1. Copia tus .pst a data/raw_pst/ (varios archivos, sin límite)
cp /ruta/pendrive/*.pst data/raw_pst/

# 2. Extrae TODOS los PST de golpe (genera checksum + log de cada uno)
bash scripts/01b_extract_all_pst.sh data/raw_pst data/eml

# 3. Parseo, adjuntos, embeddings, indexado (uv ya instalado y `uv sync` hecho)
uv run python scripts/02_eml_to_json.py --input data/eml --output data/processed/emails.jsonl --attachments-dir data/attachments
uv run python scripts/03_extract_attachments.py --emails data/processed/emails.jsonl --output data/processed/emails_enriched.jsonl
uv run python scripts/04_chunk_and_embed.py --input data/processed/emails_enriched.jsonl --output data/processed/chunks_with_embeddings.jsonl
uv run python scripts/05_ingest_qdrant.py --input data/processed/chunks_with_embeddings.jsonl --collection correos_alberto

# 4. Consulta
uv run python scripts/06_query_llamaindex.py --collection correos_alberto --interactive
```

⚠️ **Antes de lanzarlo contra los 76GB completos**, prueba primero con un solo
PST pequeño (o copia solo uno a `data/raw_pst/`) para validar que cada paso
funciona en tu entorno concreto — versión de `readpst`, credenciales de
Ollama/Qdrant, etc. Encadenar los 5 comandos sobre el histórico completo sin
haber probado antes puede hacerte perder horas si algo falla a mitad del
paso 3 o 4.

`01b_extract_all_pst.sh` procesa cada PST en su propia subcarpeta dentro de
`data/eml/<nombre_del_pst>/`, calcula el checksum SHA-256 de cada PST de
origen y deja un log en `data/processed/extraction_log.tsv` — útil para
confirmar que la copia desde el pendrive llegó íntegra antes de fiarte del
resultado.

## 1. Extraer un único PST → EML

```bash
bash scripts/01_extract_pst.sh /ruta/a/tu/archivo.pst data/eml
```

Genera `data/eml/<carpeta>/*.eml` conservando la jerarquía de carpetas del PST.

## 2. Parsear EML → JSON normalizado + adjuntos

```bash
uv run python scripts/02_eml_to_json.py --input data/eml --output data/processed/emails.jsonl --attachments-dir data/attachments
```

Cada línea de `emails.jsonl` tiene el esquema:
```json
{"id": "...", "subject": "...", "from": "...", "to": [...], "cc": [...],
 "date": "...", "folder": "...", "thread_id": "...", "body": "...",
 "attachments": ["data/attachments/xxx.pdf", ...]}
```

## 3. Extraer texto de adjuntos (PDF/DOCX/PPTX/XLSX)

```bash
uv run python scripts/03_extract_attachments.py --emails data/processed/emails.jsonl --output data/processed/emails_enriched.jsonl
```

Usa `unstructured` con fallback a extractores nativos si algún adjunto falla.

## 4. Chunking + embeddings (BGE-M3 vía Ollama)

```bash
uv run python scripts/04_chunk_and_embed.py --input data/processed/emails_enriched.jsonl --output data/processed/chunks_with_embeddings.jsonl
```

## 5. Indexar en Qdrant

```bash
uv run python scripts/05_ingest_qdrant.py --input data/processed/chunks_with_embeddings.jsonl --collection correos_alberto
```

## 6. Consultar (LlamaIndex + Qwen2.5)

```bash
uv run python scripts/06_query_llamaindex.py --collection correos_alberto --query "¿Qué se acordó con Henry Schein sobre MCP?"
```

O modo interactivo:
```bash
uv run python scripts/06_query_llamaindex.py --collection correos_alberto --interactive
```

## 7. (Fase 2, opcional) Grafo de conocimiento en Neo4j

```bash
docker run -d -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/tu_password neo4j
uv run python scripts/07_build_graph.py --input data/processed/emails_enriched.jsonl
```

Extrae personas/clientes/proyectos con el propio Qwen2.5 (extracción de
entidades estructurada vía JSON) y construye relaciones tipo:
`(Alberto)-[:HABLÓ_CON]->(Persona)-[:EN_PROYECTO]->(Cliente)`.

## Notas de rendimiento (tu hardware)

- Extracción PST + parseo: E/S limitada, no GPU. Horas para cientos de miles de correos.
- Embeddings BGE-M3 (1024-dim) en tu GB10: procesamiento por lotes, cuello de
  botella normal es I/O de adjuntos, no el modelo.
- Qdrant con filtrado por metadatos (from/to/folder/date/thread) permite
  combinar búsqueda semántica + estructurada sin re-indexar.

## Estado de este scaffold

Todo el código es funcional pero **no ha sido probado contra tus PST reales**
(este entorno no tiene acceso a Docker, GPU ni tus archivos). Recomiendo
probar primero con un PST pequeño o una carpeta exportada de prueba antes de
lanzarlo contra el histórico completo.
