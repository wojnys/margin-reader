from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

from pydantic import JsonValue

from backend.app.ai.client import Metrics, request
from backend.app.core.config import Settings
from backend.app.db.session import SessionFactory
from backend.app.knowledge.chunking import tokens
from backend.app.knowledge.embeddings import Embedder, embedder
from backend.app.knowledge.graph import GraphStore, Neo4jStore
from backend.app.modules.chat.schemas import SourcePassage
from backend.app.modules.knowledge.repository import KnowledgeRepository
from backend.app.modules.knowledge.schemas import RetrievalPlan


@dataclass
class Retrieved:
    plan: RetrievalPlan
    sources: list[SourcePassage] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    total: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0
    clarification: str | None = None


async def plan_question(
    question: str, history: list[JsonValue], config: Settings
) -> tuple[RetrievalPlan, Metrics]:
    zero: Metrics = {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0}
    page = re.search(r"\bpages?\s+(\d+)(?:\s*(?:[-–—]|to)\s*(\d+))?\b", question, re.I)
    if page:
        start = int(page[1])
        end = int(page[2]) if page[2] else start
        if end < start:
            return RetrievalPlan(
                strategy="clarify",
                query=question,
                clarification="Please provide a page range in reading order.",
            ), zero
        return RetrievalPlan(
            strategy="page" if start == end else "recap", query=question, page_start=start, page_end=end
        ), zero
    if re.search(r"\b(relationship|related|connect|connection|worked with|coach.*players)\b", question, re.I):
        return RetrievalPlan(strategy="relationships", query=question), zero
    if re.search(r"\b(summar\w*|recap|main themes|overview)\b", question, re.I):
        return RetrievalPlan(strategy="recap", query=question), zero
    # Straight factual questions need no paid planner; ambiguous follow-ups can use it.
    if re.match(r"(?i)\s*(who|what|where|when|why|how)\b", question) and not re.search(
        r"(?i)\b(he|she|they|that|it)\b", question
    ):
        return RetrievalPlan(strategy="passages", query=question), zero
    import json

    return await request(
        RetrievalPlan,
        "Plan retrieval for an uploaded book question. Always write English. Select page for one explicit page, "
        "recap for broad summaries, relationships for entity connections, passages for facts or language help. "
        "Use clarify only if the request is ambiguous or unrelated to the book. Resolve pronouns using history "
        "only when the referent is clear; history is not source evidence. Rewrite query as a standalone English search. "
        "Never invent page numbers. No external knowledge or tools. Untrusted user data:\n"
        + json.dumps({"question": question, "history": history}),
        config=config,
        max_tokens=500,
    )


def bounded(sources: list[SourcePassage], budget: int) -> list[SourcePassage]:
    selected: list[SourcePassage] = []
    used = 0
    seen: set[str] = set()
    for source in sources:
        size = tokens(source.text) + 70
        if source.id not in seen and used + size <= budget:
            selected.append(source)
            seen.add(source.id)
            used += size
    return selected


async def retrieve(
    sessions: SessionFactory,
    config: Settings,
    book_id: str,
    question: str,
    history: list[JsonValue],
    scope: dict[str, JsonValue],
    encoder: Embedder | None = None,
    graph: GraphStore | None = None,
) -> Retrieved:
    plan, metrics = await plan_question(question, history, config)
    start, end = scope.get("page_start"), scope.get("page_end")
    if isinstance(start, int) and not isinstance(start, bool):
        plan.page_start = max(start, plan.page_start) if plan.page_start is not None else start
    if isinstance(end, int) and not isinstance(end, bool):
        plan.page_end = min(end, plan.page_end) if plan.page_end is not None else end
    result = Retrieved(
        plan=plan,
        input_tokens=metrics["input_tokens"],
        output_tokens=metrics["output_tokens"],
        cost=metrics["estimated_cost"],
    )
    if plan.strategy == "clarify":
        result.clarification = plan.clarification or "Please specify which person or passage you mean."
        return result
    with sessions() as db:
        repo = KnowledgeRepository(db)
        jobs = repo.jobs(book_id)
        if not jobs:
            result.clarification = (
                "This book has not been indexed yet. Choose Index uploaded pages to prepare it for chat."
            )
            return result
        model_names = {j.embedding_model for j in jobs}
        if len(model_names) != 1:
            result.clarification = (
                "This book contains incompatible embedding versions. Reindex it with one embedding model."
            )
            return result
        model_name = next(iter(model_names))
        rows = repo.sources(book_id, plan.page_start, plan.page_end)
        result.total = len(rows)
        if not rows:
            result.clarification = (
                "No current uploaded text matches that page range. Check the page labels and indexing status."
            )
            return result
        if plan.strategy in {"page", "recap"}:
            sources = [repo.source(p, page, j) for p, page, j in rows]
            result.sources = bounded(sources, config.knowledge_evidence_tokens)
            if len(result.sources) != len(sources):
                from backend.app.knowledge.summaries import leaves, select_summaries

                summaries = leaves(repo, book_id, plan.page_start, plan.page_end)
                page_ids = {page.id for _, page, _ in rows}
                # Require coverage of every requested uploaded page, including unknown labels.
                summarized_pages = {source.page_number for source in summaries}
                if len(summarized_pages) == len(page_ids) and None not in {
                    page.page_number for _, page, _ in rows
                }:
                    result.sources = select_summaries(
                        repo, book_id, plan.page_start, plan.page_end, config.knowledge_evidence_tokens
                    )
                else:
                    result.sources = []
                if result.sources:
                    result.notes.append(
                        "This recap uses generated summaries covering the selected uploaded pages, not verbatim source quotations."
                    )
                else:
                    result.clarification = "That range exceeds the evidence budget and its summaries are not ready. Choose a smaller range or wait for indexing."
            return result
        has_vectors = any(p.embedding is not None for p, _, _ in rows)
    vector: list[float] | None = None
    if has_vectors:
        try:
            local = encoder or await asyncio.to_thread(embedder, model_name)
            vector = (
                await asyncio.to_thread(
                    local.encode,
                    [
                        "Instruct: Retrieve English book passages relevant to this question.\nQuery: "
                        + plan.query
                    ],
                )
            )[0]
        except Exception:
            result.notes.append("Semantic search is unavailable; this reply uses keyword retrieval.")
    else:
        result.notes.append("Embeddings are not ready; this reply uses keyword retrieval.")
    with sessions() as db:
        repo = KnowledgeRepository(db)
        candidates = repo.search(book_id, plan.query, vector, plan.page_start, plan.page_end)
        if plan.strategy == "relationships":
            seed_ids = {p.id for p in candidates[:8]}
            entities = list(
                {m.entity_id for m in repo.mentions(book_id) if m.passage_id in seed_ids and m.entity_id}
            )
            active_jobs = [j.id for j in repo.jobs(book_id) if j.status == "ready"]
            allowed = [p.id for p, _, _ in rows]
        else:
            entities, active_jobs, allowed = [], [], []
    if plan.strategy == "relationships":
        try:
            store = graph or Neo4jStore(config)
            graph_ids = await asyncio.to_thread(store.search, book_id, entities, active_jobs, allowed)
            with sessions() as db:
                graph_sources = KnowledgeRepository(db).by_ids(
                    book_id, graph_ids, plan.page_start, plan.page_end
                )
            candidates = graph_sources + candidates
            if not graph_ids:
                result.notes.append("No supported graph connections were found; using original passages.")
        except Exception:
            result.notes.append("Graph retrieval is unavailable; this reply uses passage search.")
    # Neighbours preserve paragraph continuity; stay within canonical range and revision.
    with sessions() as db:
        repo = KnowledgeRepository(db)
        ordered = repo.sources(book_id, plan.page_start, plan.page_end)
        mapping = {p.id: i for i, (p, _, _) in enumerate(ordered)}
        expanded: list[SourcePassage] = []
        for source in candidates[:12]:
            expanded.append(source)
            position = mapping.get(source.id)
            if position is not None:
                for neighbour in (position - 1, position + 1):
                    if 0 <= neighbour < len(ordered):
                        expanded.append(repo.source(*ordered[neighbour]))
        result.sources = bounded(expanded, config.knowledge_evidence_tokens)
    if not result.sources:
        result.clarification = "I could not find supporting passages in the selected uploaded pages."
    return result
