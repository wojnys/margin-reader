from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.app.modules.chat.schemas import SourcePassage

EntityKind = Literal["person", "team", "organization", "place", "event", "topic"]
Strategy = Literal["page", "passages", "relationships", "recap", "clarify"]


class ExtractedMention(BaseModel):
    local_id: str = Field(min_length=1, max_length=60)
    passage_id: str
    surface: str = Field(min_length=1, max_length=500)
    kind: EntityKind
    description: str = Field(max_length=1000)
    named: bool


class ExtractedClaim(BaseModel):
    subject: str
    object: str
    relation: Literal[
        "COACHES",
        "PLAYS_FOR",
        "WORKS_WITH",
        "PARTICIPATES_IN",
        "LOCATED_IN",
        "DISCUSSES",
        "RELATED_TO",
        "MET",
        "OPPOSES",
    ]
    description: str = Field(min_length=1, max_length=1500)
    passage_ids: list[str] = Field(min_length=1, max_length=6)


class ExtractedKnowledge(BaseModel):
    mentions: list[ExtractedMention] = Field(max_length=60)
    claims: list[ExtractedClaim] = Field(max_length=60)
    left_summary: str = Field(default="", max_length=2500)
    right_summary: str = Field(default="", max_length=2500)


class SectionText(BaseModel):
    text: str = Field(min_length=1, max_length=3000)


class ResolutionDecision(BaseModel):
    mention_id: str
    entity_id: str | None
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)


class Resolutions(BaseModel):
    decisions: list[ResolutionDecision] = Field(max_length=60)


class RetrievalPlan(BaseModel):
    strategy: Strategy = "passages"
    query: str = Field(min_length=1, max_length=4000)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    clarification: str | None = Field(default=None, max_length=1000)


class IndexStatus(BaseModel):
    id: str
    session_id: str
    revision: int
    status: str
    error: str | None
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    warning: str | None = None


class BookKnowledge(BaseModel):
    jobs: list[IndexStatus]
    passages: int
    entities: int
    unresolved_mentions: int


class IndexRequested(BaseModel):
    scheduled: int


class ReviewMention(BaseModel):
    entity_id: str | None = None


class MentionResponse(BaseModel):
    id: str
    surface: str
    description: str
    kind: EntityKind
    passage_id: str
    resolution: str
    entity_id: str | None
    source: SourcePassage | None = None


class EntityResponse(BaseModel):
    id: str
    name: str
    kind: str
