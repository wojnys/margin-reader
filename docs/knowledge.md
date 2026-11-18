# Book knowledge and retrieval

The reading application uses PostgreSQL + pgvector for original passages and search, Neo4j for evidence-backed relationships, LlamaIndex for passage splitting, local Qwen embeddings, and PydanticAI + DeepInfra for extraction, resolution, summaries, planning and answers. Chat replies are English. Existing saved replies are preserved in their original language; Czech learning explanations outside chat are unchanged.

## Start-up and configuration

The Compose PostgreSQL image includes pgvector and uses the PostgreSQL 18 volume path. Before replacing an existing database container, take a private `pg_dump` backup. Apply Alembic migrations before starting the application against an existing database. Keep all database backups outside source control.

Manually check your private settings using `.env.example` as the template. In particular:

- `DATABASE_URL` must point to the application PostgreSQL database.
- `NEO4J_URI=bolt://127.0.0.1:7687` and `NEO4J_USER=neo4j` target the development container.
- Set `NEO4J_PASSWORD` yourself to the development password declared in `compose.yaml` (`margin_graph_dev`), or configure your own matching credentials.
- `EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B` produces 1024-dimensional vectors locally. The first use downloads public model weights, anonymously. Changing the embedding model creates a new indexing generation; do not combine vectors from different models.
- `KNOWLEDGE_ENABLED=true` enables the new chat path. Setting it false retains the legacy text-selection path as a rollback option.
- `KNOWLEDGE_TASK_QUEUE=margin-knowledge` separates indexing from reading/chat activities.
- `KNOWLEDGE_REASONING_EFFORT=none` is the default for structured knowledge tasks. It is separate from the general chat/learning reasoning setting. No private configuration edit is required to use this default.

Commands for you to run after configuration:

```sh
docker compose --env-file /dev/null up -d --wait
uv run --locked alembic upgrade head
./scripts/dev.sh
```

Stop existing launchers first. The launcher starts API, frontend, reading worker, knowledge worker and contract watcher. For a separately managed worker:

```sh
uv run --locked python -m backend.app.temporal.knowledge_worker
```

Application: http://localhost:5187 · API: http://localhost:8017/docs · Temporal: http://localhost:8323 · Neo4j Browser: http://localhost:7474 · PostgreSQL: `127.0.0.1:5437`.

## Upload and index

New OCR text and corrected transcriptions persist an indexing request in the same PostgreSQL transaction. The existing dispatcher signals a durable `IndexBook` workflow. Each book processes its index jobs sequentially; different books can run concurrently. Existing reading/learning workflows retain their recorded activity sequences.

The indexing stages are:

1. Preserve two source pages and exact passage offsets. Recognized labels such as `14–15` supply physical page numbers. Arbitrary labels are retained but cannot satisfy numeric range queries.
2. Split with LlamaIndex SentenceSplitter (400-token target, 50-token overlap).
3. Generate local normalized embeddings and PostgreSQL full-text indexes.
4. Extract structured mentions and evidence-backed claims through DeepInfra. The model selects numbered source-token ranges; Python reconstructs each mention's exact original text, including OCR line breaks. Token ranges and supplied IDs are validated. Semantic accuracy still requires evaluation/review.
5. Retrieve candidate identities using named mentions, descriptions and passage similarity. Ask the LLM to resolve them using evidence, or retain ambiguity. Prior unresolved mentions are revisited in bounded batches when new context arrives. Topic/event occurrences can have their own nodes without a proper name; this does not identify a generic person such as “the coach”.
6. Cache page summaries and combine them into fixed page buckets (10 pages, then 50, 250, etc.). Only changed summary branches require new calls. These derived recaps are optional: an AI-provider/validation failure produces a visible warning and still permits publishing the validated graph. A later indexing job can build the missing summaries; long recaps continue to require complete source coverage.
7. Synchronize the job's claims into Neo4j and mark it ready.

Indexing model outputs are cached by job/stage. A graph outage can be retried without repeating completed extraction. This is not an exactly-once billing guarantee: a crash after an external provider responds but before the result commits can still cause a duplicate call.

Extraction uses short `P1`, `P2`, etc. passage labels and numbered word/punctuation tokens in model requests. Python resolves the passage labels to database UUIDs and reconstructs mention surfaces from the selected inclusive token boundaries. Free-form surface names are not accepted in model output; out-of-range/reversed spans and unknown references fail validation. Rejected outputs retain field-level diagnostics (or a distinct token-limit error), without saving full model responses in Temporal errors. Usage returned by the provider is recorded for failed validation too. After the model's single correction attempt, a core extraction/resolution validation error fails the activity without further Temporal retries; an explicit retry remains available after correcting the problem.

Graph extraction has a 12,000-token completion ceiling, resolution 6,000, and section recaps 4,000. These are ceilings, not requests to generate that many tokens; prompts still ask for compact output. Earlier live failures showed that increasing caps alone did not reliably prevent reasoning from consuming the budget. Knowledge tasks now explicitly request `reasoning_effort=none` by default. Provider-specific behavior and semantic quality still require live evaluation. The underlying provider's reported usage determines estimated cost.

`IndexBook` serializes each book's jobs, then closes after 30 idle seconds. Successful batches complete; a batch with failed jobs processes the rest of its queued items and then ends Failed. Later uploads use signal-with-start with explicit ID reuse to start a fresh run under the same book ID. Duplicate signals for the active job are suppressed. Its `state` query exposes active/pending jobs and failures. Failure-persistence activities have bounded retries and a two-minute schedule-to-close limit. Continue-as-new carries pending jobs and failure outcomes after 25 jobs. A Temporal patch preserves replay of pre-fix histories; it deliberately retains their original behavior during replay.

Older versions kept the per-book coordinator open indefinitely, so Running duration could include days of idle waiting. Pre-fix histories remain replay-compatible. Failed database jobs are not automatically retried by an application upgrade; use the explicit indexing action after reviewing their errors.

Existing books are not silently sent for paid backfill. In Book chat, choose **Index uploaded pages / retry · uses AI credits**. The panel displays progress and estimated recorded usage. Public model downloads and local embedding compute do not use DeepInfra credit; extraction, resolution and generated summaries do.

## Data and revisions

New tables: `knowledge_jobs`, `knowledge_pages`, `knowledge_passages`, `knowledge_entities`, `knowledge_mentions`, `knowledge_claims`, `knowledge_summaries`, `knowledge_sections`. Chat turns gain scope and retrieval metadata; readings track their active knowledge job.

The text fingerprint includes source text and page label, not the learning revision. Regenerating expressions alone therefore does not reindex identical text. Source corrections switch the active job. Old passage versions remain available for saved citations, but current retrieval excludes them. Claim evidence and inferred identity evidence must be within the allowed current source set for graph retrieval.

PostgreSQL owns canonical knowledge records. Neo4j is a rebuildable projection. There is no cross-database transaction; job status and retryable synchronization handle partial failures. Historical Neo4j claims can remain physically present, but retrieval restricts itself to current ready jobs and validates returned passage IDs against PostgreSQL.

## Chat behavior

- Explicit page requests use direct lookup without embedding search or a planner call.
- Factual questions use PostgreSQL full-text and exact vector search, fused using reciprocal rank fusion. Exact vector search avoids approximate-index filtering surprises for this initial per-book workload. Reranking is not enabled by default.
- Relationship questions use retrieved mentions to seed a bounded two-hop Neo4j traversal, then fetch original supporting passages. Neo4j failures are reported as a fallback note, not hidden.
- Recaps use original passages if the range fits. Larger ranges use cached generated summaries only when all selected uploaded pages are covered. Generated summaries are explicitly labelled in the answer/citation UI; they are not presented as author quotations. If coverage or budget is insufficient, the application asks for a smaller range.
- Ambiguous follow-ups can use a small structured DeepInfra planning call. English is always requested for new answers, regardless of legacy thread language.
- Page range fields intersect any range inferred from the question. Claims relying on identity evidence outside that scope are excluded.

Evidence is bounded before answering (default 6000 approximate tokens), history is separately bounded, and retrieved sources are snapshotted for retries. Token counting uses cl100k as a conservative working approximation, not DeepInfra's exact billing tokenizer.

All database and graph queries are server-owned and parameterized. The LLM cannot execute arbitrary SQL/Cypher. Book scope comes from the existing authorized chat/thread, not an LLM-supplied book ID. Current authorization remains the application's local owner cookie, not a newly introduced multi-user login system.

## Reference review

Choose **Review person references** to inspect inferred/unresolved mentions and their source passages. Select an existing entity of the same kind or leave the reference unresolved. Both kinds of manual review take precedence over automatic decisions, including later uploads. A manual link retains source evidence for its target identity so page limits still apply. Reviewed changes queue projection synchronization and reuse cached extraction.

This pipeline reduces common identity mistakes; it does not guarantee perfect book-length coreference. Test competing people with the same role, quoted speech, flashbacks and missing pages before trusting automatic links.

## Verification without paid APIs

```sh
uv run --locked pytest -q
POSTGRES_TESTS=1 GRAPH_TESTS=1 TEMPORAL_TESTS=1 uv run --locked pytest -q
uv run --locked basedpyright
uv run --locked ruff check backend/app
cd frontend
npm test
npm run api:check
npm run build
```

Database/Temporal integration tests create synthetic data and mock the LLM. PostgreSQL tests use disposable databases; graph tests clean only their generated book IDs. `scripts.preview_chat` provides a synthetic UI server on port 8097 with a prepared English reply and mocked planning, using temporary SQLite and no paid model calls. Production build uses `envDir: false` on the frontend; provider secrets remain server-side.

A live DeepInfra quality check on real book passages is a separate operation requiring explicit authorization. Automated citation validation verifies source IDs and text membership; it cannot prove every interpretation is semantically correct.
