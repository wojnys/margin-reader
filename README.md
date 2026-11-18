<p align="center">
  <img src="docs/assets/margin-banner.svg" alt="Margin — read between the lines" width="100%" />
</p>

<p align="center">
  <a href="https://github.com/wojnys/margin-reader/actions/workflows/checks.yml"><img src="https://github.com/wojnys/margin-reader/actions/workflows/checks.yml/badge.svg" alt="Checks" /></a>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white" alt="React 19" />
  <img src="https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/Runs-locally-214F40" alt="Runs locally" />
</p>

**Margin** is a local reading and language-learning application for English learners, with Czech explanations and vocabulary practice. It connects the book in your hands to a reading workspace on your computer—and lets your phone handle the photographs.

Instead of translating an entire book, Margin helps you understand uploaded pages through clear English summaries, useful expressions, real-life examples and conversations grounded in the text.

**Photograph → understand → save useful expressions → practise later.**

[Get started](#run-locally) · [How it works](#how-it-works) · [Architecture](#architecture) · [Development guide](docs/development.md) · [Knowledge indexing](docs/knowledge.md)

## What you can do

| Feature | What it does |
| --- | --- |
| **Read with clarity** | Separate B1-English summaries for the left and right page, plus a short topic title. |
| **Learn useful English** | Extract 10–22 B1–C1 expressions, collocations and phrasal verbs with Czech explanations and fresh examples. |
| **Use it in conversation** | Generate teaching examples for work, friends and everyday situations. |
| **Capture from your phone** | Scan a QR code and upload photographs over the same Wi-Fi. Review, reorder and label up to 10 two-page photographs. |
| **Build your expression library** | Save expressions and practise recall with scheduled self-assessment. |
| **Ask about your book** | Saved English conversations, expandable source citations and optional page-range limits. |
| **Explore connections** | Incrementally extract entities and supported relationship claims into Neo4j; review uncertain references. |
| **Keep reading while jobs run** | Temporal manages background processing, retries and saved progress. |

An original **sample reading** is included. Its prepared content can be explored without making paid AI requests.

## How it works

```mermaid
flowchart TD
    Photo[Book photo from desktop or phone] --> OCR[Local RapidOCR]
    OCR --> Text[Original page text in PostgreSQL]
    Text --> Learning[DeepInfra: summaries, expressions and learning cards]
    Text --> Passages[Exact passages and local embeddings]
    Passages --> Search[PostgreSQL full-text search and pgvector]
    Passages --> Extract[DeepInfra: source-grounded entities and claims]
    Extract --> Graph[Neo4j knowledge graph]
    Question[Your book question] --> Route[Choose a retrieval strategy]
    Route --> Text
    Route --> Search
    Route --> Graph
    Route --> Recaps[Cached recaps for longer ranges]
    Text --> Recaps
    Text --> Evidence[Selected supporting evidence]
    Search --> Evidence
    Graph --> Evidence
    Recaps --> Evidence
    Evidence --> Answer[English answer with source citations]
```

**OCR and embeddings run locally.** Photographs stay on your computer. Text needed for the requested AI task is sent to DeepInfra; the application is local-first, not fully offline.

Chat selects evidence rather than sending the whole book for every question:

- **A specific page:** direct page lookup.
- **A factual or language question:** combined keyword and semantic search.
- **A relationship question:** bounded graph traversal followed by original supporting passages.
- **A longer recap:** cached summaries when they cover the selected pages.

Citations retain their reading, page side and source-text snapshot. Source validation checks provenance; it does not prove every model interpretation is correct.

## Run locally

### 1. Prerequisites

- [Docker Desktop / Docker Compose](https://docs.docker.com/compose/install/), with Docker running.
- [Node.js](https://nodejs.org/) **24** and npm. With nvm, run `nvm install && nvm use` in the project root.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for Python dependencies and commands. uv can download Python **3.12** automatically.
- A [DeepInfra](https://deepinfra.com/) API key for processing your own pages and generating chat replies. Prepared sample content does not require a paid request.

### 2. Clone and configure

```bash
git clone https://github.com/wojnys/margin-reader.git
cd margin-reader
uv sync --locked
```

Create your private `.env` from [`.env.example`](.env.example) **only if you do not already have one**, then set:

```dotenv
DEEPINFRA_API_KEY=YOUR_DEEPINFRA_API_KEY
DATABASE_URL=postgresql+psycopg://margin:margin_local_dev@127.0.0.1:5437/margin
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=margin_graph_dev
```

These database credentials match the **public local-development defaults** in `compose.yaml`. Database ports bind to loopback. Use your own credentials and deployment configuration outside local development. Never put provider credentials in frontend code or `VITE_` variables.

The template also exposes model selection, cost estimates, Temporal queues and knowledge-indexing settings. Changing `DEEPINFRA_MODEL` does not regenerate saved readings.

### 3. Start

```bash
./scripts/dev.sh
```

The launcher installs missing frontend dependencies, starts the containers, applies migrations, and runs FastAPI, React, both workers and the OpenAPI watcher.

| Service | Address |
| --- | --- |
| **Web application** | **[localhost:5187](http://localhost:5187)** |
| FastAPI / OpenAPI docs | [localhost:8017/docs](http://localhost:8017/docs) |
| Temporal dashboard | [localhost:8323](http://localhost:8323) |
| Neo4j Browser | [localhost:7474/browser/](http://localhost:7474/browser/) |
| PostgreSQL | `127.0.0.1:5437` |

Neo4j Browser connects to `bolt://localhost:7687` with username `neo4j` and development password `margin_graph_dev`.

`Ctrl+C` stops application processes owned by the launcher. Docker volumes preserve database records, graph data and workflow history. Uploaded images stay in the host's `data/` directory. To stop containers without removing their data:

```bash
docker compose --env-file /dev/null stop
```

### 4. Try a reading

1. Open the app on your computer and choose the prepared sample, or create a book.
2. Upload a JPEG, PNG or WebP photograph of two open pages. Convert HEIC photographs first.
3. Review the transcription, summaries and expressions; correct OCR text when needed.
4. Save useful expressions and practise them later.
5. Open **Book chat**, select your book and ask about its uploaded pages.

New OCR text automatically schedules knowledge indexing. **Index uploaded pages / retry** prepares older readings or retries failed stages; it uses AI credits. Indexing is sequential within each book, and its workflow closes after 30 idle seconds. Later uploads can start a new run.

For phone capture, choose **Connect your phone**, scan the QR code and use the capture page while your phone and computer are on the same reachable Wi-Fi network. This is a file-upload page, not a live camera stream.

## Architecture

| Layer | Technology / responsibility |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, TanStack Query |
| API | FastAPI, Pydantic, feature-based routers, services and repositories |
| API contract | FastAPI OpenAPI → Orval → generated TypeScript clients and query hooks |
| Persistence | SQLAlchemy, Alembic, PostgreSQL 18 and pgvector |
| Background work | Temporal workflows and activities; separate reading/chat and knowledge workers |
| Text recognition | Local RapidOCR with ONNX Runtime |
| Retrieval | LlamaIndex passage splitting, local Sentence Transformers embeddings and PostgreSQL full-text search |
| Graph | Neo4j; book-scoped entities and evidence-backed claim nodes |
| AI communication | PydanticAI and DeepInfra's OpenAI-compatible API |
| Quality checks | Strict BasedPyright, Ruff, pytest and frontend transport/build checks |

```text
backend/app/
  api/             HTTP routing and dependencies
  core/            Configuration, access checks and errors
  db/              ORM models, sessions and unit of work
  modules/         Books, readings, chat, knowledge, vocabulary, practice, capture
  knowledge/       Chunking, embeddings, extraction, retrieval and graph adapter
  ai/              Typed provider requests and output validation
  temporal/        Workflows, activities, dispatcher and workers
frontend/src/
  app/             Application composition and providers
  pages/           Page-level screens
  features/        Feature-specific components and behavior
  api/generated/   Orval-generated clients, hooks and types
  components/      Shared interface components
contracts/         Generated OpenAPI specification
migrations/        Alembic database history
tests/             Backend, contract and integration tests
```

All books share one PostgreSQL database and one Neo4j database. Book IDs scope retrieval; no separate database is needed for each book. PostgreSQL owns canonical source records; Neo4j is a rebuildable projection.

## Development and tests

Backend checks use dummy configuration and mocked AI responses by default:

```bash
uv run --locked pytest -q
uv run --locked ruff check backend/app
uv run --locked ruff format --check backend/app
uv run --locked basedpyright
```

Frontend checks:

```bash
cd frontend
npm ci
npm run api:check
npm test
npm run build
```

With the development containers running, opt into synthetic integration tests:

```bash
POSTGRES_TESTS=1 GRAPH_TESTS=1 TEMPORAL_TESTS=1 uv run --locked pytest -q
```

These integration tests mock AI calls. The manual `scripts.verify_live` check uses paid credit and is not part of the default suite. See the [development guide](docs/development.md) for separate service commands and SQLite migration instructions.

## Scope, privacy and current limitations

- **Local development application.** The owner cookie and limited phone-upload links are not a multi-user authentication system. Do not expose the development stack directly to the public internet.
- **AI requests cost money.** OCR and embeddings are local; generation, graph extraction and some query planning use DeepInfra. Estimates depend on configured prices; the provider dashboard is authoritative.
- **Review the source.** OCR, entity resolution and interpretations can be wrong. Ambiguous references can remain unresolved. Corrected source text creates a new indexing generation.
- **The graph vocabulary is restricted.** It is not an automatic, unrestricted ontology for every book genre. A richer relationship registry is a possible improvement, not an implemented feature.
- **Page scope uses uploaded labels.** Numeric ranges need recognizable labels. The app cannot answer from pages you have not uploaded.
- **Private files stay private.** `.env` variants, uploads, databases, backups, caches and machine-specific agent hooks are excluded from Git. Only the placeholder `.env.example` belongs in source control.

Implementation details: [Development guide](docs/development.md) · [Knowledge indexing](docs/knowledge.md).
