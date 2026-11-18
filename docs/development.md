# Development guide

A local reading companion for a Czech learner of English.

**Photograph → understand → save useful expressions → practise later.**

React + TypeScript / npm · FastAPI + Python / uv · SQLAlchemy + Alembic · PostgreSQL · Temporal · RapidOCR · PydanticAI + DeepInfra.

Book chat now supports persistent passages, pgvector hybrid search, Neo4j relationship retrieval,
incremental knowledge indexing and English replies. See the [knowledge setup and architecture](knowledge.md)
for the new worker, private settings to update manually, indexing costs and verification commands.

## Start locally

Run the commands in this guide from the project root. Requirements: Docker running, Node.js 24 (`nvm install && nvm use`; minimum 22.18 for Orval), npm, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.12 is downloaded automatically by uv when needed.

1. Copy `.env.example` to `.env` **only if `.env` does not already exist**.
2. Set `DEEPINFRA_API_KEY` and `DATABASE_URL` in `.env` using `.env.example`. Never put the key in a `VITE_` variable, a frontend file, or source control. Existing SQLite installations must follow **Database and PostgreSQL** below before switching the URL.
3. Run:

```sh
./scripts/dev.sh
```

- Reading room: **http://localhost:5187**
- API documentation: http://localhost:8017/docs (owner cookie required for protected endpoints)
- Temporal dashboard: http://localhost:8323
- PostgreSQL: `127.0.0.1:5437` (database port, not a browser URL)

Ctrl+C stops the frontend, API, and worker owned by the launcher. PostgreSQL data and Temporal history stay in separate Docker volumes. Stop containers with `docker compose --env-file /dev/null stop`; do not remove their volumes if you want to retain data.

The ports are deliberately separate from the common 5173 / 8000 / 7233 ports, which may already be used by other projects.

To run the pieces separately, from the project root:

```sh
uv sync --locked
docker compose --env-file /dev/null up -d --wait
uv run alembic upgrade head
uv run uvicorn backend.app.main:create_app --factory --host 0.0.0.0 --port 8017 --reload
# Another terminal, project root:
uv run python -m backend.app.temporal.worker
# Another terminal, project root:
uv run python -m backend.app.temporal.knowledge_worker
# Another terminal:
cd frontend
npm ci
npm run dev
```

Install uv and make sure it is on PATH before running these commands. A machine-local `.tools/uv` fallback is supported by the launcher but is not bundled in the repository.

## Reading workflow

1. Create a book with title, author, B1/B2/C1 learner level, and optional context notes.
2. Upload a JPEG, PNG, or WebP photograph containing **both open pages**, up to 20 MB. HEIC must be converted first.
3. The worker uses **local RapidOCR** to extract separate English text from each page. No photograph is sent to DeepInfra for OCR. One DeepInfra call then creates two clear B1-English page summaries, **10–22 expressions**, and comprehension cards with Czech answers. It aims for 18–22 expressions when the pages contain enough useful material.
4. Review the original photograph and transcription. Correcting the text creates a new revision and regenerates its summaries and learning material. The Expressions tab can also regenerate learning material from the saved transcription without re-uploading or re-running OCR. Previously saved vocabulary retains its original source snapshot.
5. Save individual expressions to the library. Practice recalls the English phrase from a Czech meaning; reveal the answer and honestly rate recall. Reviews are scheduled using a simple interval system, with “Again” due after ten minutes. This is self-assessed recall, not automated grading.

“Explore a sample reading” loads an original tutorial with prepared content. It is labelled as a sample and makes **no AI calls**.

## Book chat

Open **Book chat** in the main navigation, choose a book, and start a saved conversation.
New replies are always in clear English. Each thread stays bound to its
book; changing the book selector shows that book's conversations. Original extracted/corrected
page text is used as evidence. Optional **From page / Through page** limits restrict retrieval,
including the supporting passages for graph identity links. Existing books need indexing first;
use the **Book knowledge** panel to start backfill and inspect progress or unresolved references.

Each submitted question creates a durable pending turn. The dispatcher starts `AnswerBookChat`
and the Temporal worker generates a typed answer through PydanticAI/DeepInfra. The frontend polls
while a reply is active; it does not stream tokens. You can leave and reopen a saved conversation.
One active reply per thread and client request identifiers prevent accidental duplicate submissions.
Failures allow explicit retries, with attempt guards against stale activity completions. Replies
use a 4,096-token output budget and store successful-request token usage and estimated cost.

Questions select a retrieval strategy: direct page lookup, PostgreSQL keyword + pgvector semantic
search, Neo4j relationship retrieval, or cached hierarchical recaps for long page ranges. Original
evidence has a configurable approximate token budget; recent history has a separate 2,000-token
budget. The LLM receives selected evidence rather than the entire book. Generated recap sources
are visibly labelled and are never presented as author quotations. Answers do not use other books
or external sources. See [Book knowledge and retrieval](knowledge.md) for setup, data flow,
incremental identity resolution, costs and current limitations.

Each reply saves immutable source snapshots with reading IDs, revisions, page labels, and page
sides. The model selects short evidence labels (E1, E2, ...); Python resolves these labels and
copies their exact text into citations, avoiding fragile model copying of long IDs and OCR text.
Unknown labels receive one PydanticAI correction attempt before Temporal retries the activity.
Citation IDs and exact quotation matches are validated before persistence. Expand citations
to read the supporting excerpt or open the original reading. Quotation validation checks provenance,
not whether every interpretation is correct. Responses may report that the excerpts lack evidence.
Existing owner-cookie authorization protects every chat endpoint; multi-user authentication remains
a separate future feature. Quizzes and learning reports are not included in this chat release.

Migration `8c3fb4e063d2` adds `chat_threads` and `chat_turns`; `9d4c28a6e1f0` adds versioned
knowledge records and retrieval metadata. Run migrations and restart the API and workers before
using the new retrieval pipeline. For an entirely isolated UI smoke test,
run `.venv/bin/python -m scripts.preview_chat` and open `http://localhost:8097`; this uses synthetic
book content, dummy settings, a temporary database, and a prepared reply with no provider calls.

## Conversation examples

New reading jobs prepare an optional Conversation section after the core learning material. It selects
up to three reusable expressions from the saved expression list, explains their meaning, grammatical
pattern and register in Czech, and creates English/Czech examples for work, friends and everyday errands.
The examples are labelled as newly generated teaching material; source quotations are copied from the
saved expression records, never supplied by the example generator.

This is a separate Temporal activity and an additional paid text request. A conversation failure does
not discard the summaries or expressions. Existing completed readings are not backfilled automatically:
open Conversation and choose Create examples. Retrying reuses successful output for the same revision.
Editing the transcription or regenerating learning creates a new revision, keeping old examples separate.

Conversation jobs and cards use the new `conversation_sets` and `conversation_expressions` tables in
the existing application database. Apply the new migration before restarting API and worker:

```sh
uv run alembic upgrade head
./scripts/dev.sh
```

Stop the old launcher first. The launcher already runs migrations as part of startup. Migration and
startup commands load your private runtime settings; isolated tests and contract generation do not.

## Phone camera over Wi-Fi

Open the main app on **localhost on the computer**, select a book, and choose **Connect your phone**. Scan its QR code from a phone on the same Wi-Fi. The link is a random, single-use upload capability that expires in 15 minutes. It permits uploading one batch of photographs to that book; it does not permit browsing the book library or accessing the API key.

The phone opens the computer's LAN address, never `localhost`. If automatic detection selects the wrong network adapter, set `PHONE_BASE_URL=http://YOUR_COMPUTER_IP:5187` in `.env` and restart the API. Allow the app through the local firewall and keep the computer awake. Guest Wi-Fi with client isolation will not work.

The phone capture page accepts a batch of up to ten spread photographs. Take photographs one at a
time using the rear-camera picker or select multiple images from the library. Review the thumbnails,
remove or reorder photographs, set the first page number, and edit individual page labels before sending.
Six spread photographs become six independent reading sessions (up to twelve pages), preserving your
chosen order. A link can submit one batch; the original single-photo endpoint remains compatible.

Each photograph is limited to 20 MB and a batch to 80 MB combined. The API also limits incoming
multipart bytes while streaming, closes partially spooled files on oversized requests, and accepts the
whole batch atomically: invalid images or a competing upload roll back all reading rows and uploaded
files, without consuming an otherwise unused link. Pending reading rows are committed together, then
the existing dispatcher starts one Temporal workflow per spread. The worker permits two activities
at once, so processing overlaps within that bound rather than making ten simultaneous paid requests.

Every image in a batch receives the same previously completed reading context. It does not wait for,
or use summaries from, future spreads in the batch. New learning results also include a short English
topic title generated in the same summary call. Titles appear with page numbers; old readings retain
their page labels until explicitly regenerated. No title backfill or extra title-only API call occurs.

The first version uses the phone's native file/camera picker with a gallery fallback. Browser support for the capture hint varies. No live camera stream, native phone app, or HTTPS certificate setup is required for ordinary file uploads. The main application is designed for your trusted local network, not public internet exposure.

## Project layout and type checks

```text
backend/app/
  main.py                    # import-safe app factory; runtime resources start in lifespan
  api/                       # router aggregation and dependency injection
  core/                      # settings, owner access, errors, runtime dependencies
  db/                        # ORM base, model registry, session factory, unit of work
  modules/
    books/                   # router.py, schemas.py, service.py, repository.py, models.py
    readings/                # same layers, plus image handling and durable processing
    vocabulary/
    practice/
    capture/
  ai/                        # PydanticAI adapter and validated LLM outputs
  temporal/                  # workflows, activities, dispatcher, worker
  tools/                     # offline OpenAPI exporter and source watcher
frontend/src/
  app/                       # composition, providers, navigation/dialog state
  pages/                     # reading, vocabulary, practice, phone capture
  features/                  # reading queries/components and book form conversion
  components/                # shared UI and layout
  api/generated/             # Orval clients, React Query hooks, and TypeScript models
  api/transport.ts           # shared fetch transport, credentials, errors, cancellation
  styles/
contracts/openapi.json       # generated, committed API contract
migrations/                  # existing Alembic history; unchanged table definitions
tests/                       # isolated backend, contract, and migration checks
```

The root `pyproject.toml` and `uv.lock` manage the Python application, worker, migrations, and tests together. This keeps one environment and avoids duplicate project configuration. The two old executable paths (`backend.main:app`, `python -m backend.worker`) remain tiny compatibility entry points.

Routers handle HTTP only. Services own business rules and transaction commits through `UnitOfWork`; repositories contain SQLAlchemy queries and flush changes without committing. A request shares one session across its repositories, allowing an upload and phone-link claim to commit atomically. The worker releases its database session before awaiting DeepInfra.

BasedPyright checks all application code in **strict** mode, including `reportAny` and `reportExplicitAny`. Ruff enforces function annotations with `ANN`, linting, imports, and formatting. Local variable types may be inferred. Two narrow, commented type-check exceptions adapt untyped ASGI/socket interfaces; business logic does not use blanket ignores. Pydantic validates HTTP inputs, response contracts, and AI outputs at runtime. Install the recommended BasedPyright and Ruff editor extensions for immediate feedback.

```sh
uv run --locked basedpyright
uv run --locked ruff check backend/app
uv run --locked ruff format --check backend/app
```

## OpenAPI and Orval

**Python endpoint + Pydantic request/response model → OpenAPI → Orval → typed frontend requests and React Query hooks.** There is no second handwritten API specification. Keep stable explicit `operation_id` values and feature tags on routes; changing an operation ID also changes its generated TypeScript function name. API URLs stay under `/api` without a version prefix.

From `frontend/`:

```sh
npm run api:generate   # export Python contract, then generate and format TypeScript
npm run api:watch      # watch Python files; export in a fresh process; Orval watches the JSON
npm run api:check      # fail for stale contract or clients (regenerates stale clients for review)
npm run typecheck
npm test
npm run build
```

`./scripts/dev.sh` starts the API watcher alongside the API, worker, and frontend, so saving a route or schema regenerates the frontend contract. Standalone `npm run dev` needs `npm run api:watch` in a second terminal. The watcher retains the last valid schema if Python contains an error and retries on the next edit. Worker code changes require restarting the worker.

Do not edit `contracts/openapi.json` or `frontend/src/api/generated/` manually. Commit both generated outputs with backend changes. CI checks regeneration, strict Python types, lint/format, backend tests, frontend transport tests, and the production build. The frontend uses the generated clients and React Query hooks; only the common fetch transport is handwritten. Multipart requests keep the browser-generated boundary; cookies and abort signals are preserved.

The exporter creates an app **without running its lifespan**. Imports do not load settings, open the database, create upload directories, connect to Temporal, or call DeepInfra. Tests inject dummy settings and temporary databases. Schema generation and tests do not need `.env` or a provider key. Only explicitly starting the real API/worker or running migrations loads private runtime settings. The launcher no longer creates or copies `.env` automatically.

The pinned Orval dependency uses a patched `minimatch` override for its documentation dependency; `npm audit` is clean for the current lockfile.

## Architecture and recovery

```text
React browser → FastAPI → application database + local photo files
                     └→ persistent pending jobs → Temporal service
                                                   └→ Python worker
                                                       ├→ RapidOCR (local CPU OCR)
                                                       └→ PydanticAI → DeepInfra (one text-only learning call)
```

- API and worker are separate processes in the same Python project.
- FastAPI commits an upload before a background dispatcher submits it to Temporal. Pending rows act as a persistent outbox; a Temporal outage doesn't silently discard an accepted photograph.
- Workflow IDs include reading ID, revision, and explicit retry attempt. The dispatcher deduplicates submissions.
- Workflow code performs only deterministic orchestration. API calls and database operations happen inside activities.
- Each activity has a timeout, heartbeat, and bounded retry policy. Authentication, balance, invalid input, and unreadable-photo errors stop for intervention.
- Successful stage outputs are cached with a unique `(session_id, revision, stage)` constraint. Retrying a later failure reuses completed stages.
- A crash after the provider finishes but before the result is committed can still cause a repeated paid request. Temporal does not provide exactly-once billing for an external API. Local OCR has no provider charge.
- Images stay on disk. Only IDs enter Temporal workflow arguments, keeping photographs and long passages out of workflow payloads.
- The app snapshots up to three previous completed summaries and reader notes as book context. It does not retrieve the full book or deliberately use future pages. For best continuity, process spreads in reading order and wait for the previous one to finish.
- Generated vocabulary quotations and comprehension evidence must match the extracted source. This checks provenance, not every aspect of summary quality or interpretation. Review ambiguous passages.

## DeepInfra and cost

Default model: `deepseek-ai/DeepSeek-V4.1-Flash-1017`, using the compatible chat-completions endpoint at `https://api.deepinfra.com/v1/openai`. PydanticAI validates typed outputs and can request a correction when JSON or source quotations are invalid. The key is read server-side through Pydantic Settings.

The DeepInfra Chat Completions endpoint accepts named reasoning levels: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`. Margin defaults to `DEEPINFRA_REASONING_EFFORT=low`, with temperature 1.0 and top-p 0.95. The previous setting `1` is converted to `low` for compatibility with existing private configuration. Other numeric settings are rejected locally. This does not guarantee zero reasoning tokens.

The current DeepSeek promotional standard-tier rates are $0.098 per million input tokens and $0.294 per million output tokens. They can change; keep the configured estimates aligned with DeepInfra. Switching models does not recalculate old saved costs or regenerate existing readings. The switch was tested with mocked API responses; image transcription and Czech quality on this exact model have not yet been evaluated live.

The UI reports estimated usage for successfully persisted stages using configurable input/output prices in `.env`. Failed requests, requests lost before persistence, or additional provider-specific charges may not be recorded. **DeepInfra's billing dashboard is authoritative.** Set provider spending limits there if desired. The application has no automatic wallet top-up.

Only OCR text and selected reading context are sent to DeepInfra. Photographs stay on the computer and are processed locally; application data, vocabulary, and review history also remain local. Photos are resized and re-encoded to JPEG, dropping EXIF/location metadata.

Restart **both API and worker** after changing `.env`, the model, or prompt code. The frontend never needs the API key.

## Database and PostgreSQL

The application defaults to PostgreSQL 18 in Docker on `127.0.0.1:5437`, database/user `margin`.
`compose.yaml` contains the public **local-development** password `margin_local_dev`; it is not a
production secret or deployment configuration. The port is bound to loopback. The PostgreSQL 18
named volume mounts `/var/lib/postgresql`, with versioned data below it. Stop/start preserves data;
`docker compose down -v` destroys database and Temporal volumes and must not be used to restart.

Tables store books, reading sessions, generated results and usage, vocabulary, review history,
phone links, conversation examples, and saved chats. SQLAlchemy uses psycopg for PostgreSQL;
timestamps remain naive UTC. No transaction is held during an LLM request. SQLite support remains
for isolated tests and recovery of previous installations, but it is no longer the default.

**Transfer an existing SQLite installation:**

1. Stop the API and Temporal worker to prevent new writes; the Temporal service may stay running.
2. Start PostgreSQL and transfer all application tables:

```sh
docker compose --env-file /dev/null up -d --wait postgres
uv run --locked python -m scripts.migrate_postgres
uv run --locked python -m scripts.migrate_postgres --verify-only
```

The command defaults to `data/margin.db` and the local development PostgreSQL URL. It does not load
runtime settings or private dotenv files. `--source PATH` and `--target-url URL` support explicit
alternatives; avoid placing production secrets in shell history. It opens SQLite read-only with a
consistent transaction, requires the current Alembic schema and valid source foreign keys, creates
the PostgreSQL schema through the existing Alembic history, and inserts in foreign-key order.
All rows are compared by primary key and full typed content, including Czech text, nested JSON,
SQL NULL versus JSON null, booleans, timestamps and IDs, before the PostgreSQL transaction commits.
Failures roll back the target transaction. A populated target is refused; the command never
overwrites or merges existing application data. `--verify-only` compares without changing rows.

3. Manually set this line in your private `.env`, matching the public development container:

```text
DATABASE_URL=postgresql+psycopg://margin:margin_local_dev@127.0.0.1:5437/margin
```

4. Restart **both API and worker** using `./scripts/dev.sh`. Both must use the same database.
   Existing private settings override the new default until you update them yourself.

This is a one-time snapshot, not replication. If SQLite writers were active during a transfer,
do not switch blindly: stop writers and verify again. On a mismatch, keep SQLite active and use
a fresh PostgreSQL database for a new transfer rather than overwriting the existing target.
The original SQLite file is retained. Uploaded photographs remain in `data/uploads`; their paths
are copied unchanged. Retain the existing data directory and owner secret. Temporal's own dev
server SQLite history remains in its separate volume; it is not the application database.

Before cutover you can revert by leaving the SQLite URL unchanged. After PostgreSQL accepts new
writes, switching back to SQLite loses visibility of those new writes; it requires a separate
reverse data transfer. PostgreSQL backups should use `pg_dump`/`pg_restore`, not copies of a running
volume. Back up uploads separately and keep backups of book data private.

Schema changes use Alembic from day one:

```sh
uv run alembic revision --autogenerate -m "Describe the schema change"
# Review the generated migration before applying it.
uv run alembic upgrade head
```

Treat `data/owner.secret` as a local access secret. Private dotenv files and local data are excluded
from source control; never include private dotenv files in an agent-operated backup.

## Verification

```sh
uv run --locked pytest -q
# Disposable PostgreSQL schema/data/API tests against the local container, no paid AI calls:
POSTGRES_TESTS=1 uv run --locked pytest -q tests/test_postgres_migration.py
# Actual Temporal retry and deterministic-history replay, no paid AI calls:
TEMPORAL_TESTS=1 uv run pytest -q tests/test_temporal.py
cd frontend
npm test
npm run api:check
npm run build
```

Tests isolate database state and mock DeepInfra; they never use the real API key. The opt-in Temporal test uses a unique task queue on the local service and simulates a provider failure.

For a manual **paid** end-to-end test with an original sample photograph, start all services, then run `uv run python -m scripts.verify_live`. This makes real DeepInfra requests and saves a “Live API check” reading in the sample book. The image renderer in that script currently uses the macOS Georgia font path.

For a single-server build, run `npm run build` in `frontend`, then restart the API. FastAPI serves the built React app at http://localhost:8017, including `/capture/...` phone routes. Run the Temporal worker separately as before.
