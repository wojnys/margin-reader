from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CreateThread(BaseModel):
    language: Literal["cs", "en"] = "en"


class ThreadResponse(BaseModel):
    id: str
    book_id: str
    title: str
    language: Literal["cs", "en"]
    created_at: str


class SendMessage(BaseModel):
    request_id: UUID
    question: str = Field(min_length=1, max_length=4000)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def check_range(self) -> SendMessage:
        if self.page_end is not None and self.page_start is None:
            self.page_start = 1
        if self.page_start is not None and self.page_end is not None and self.page_end < self.page_start:
            raise ValueError("The last page must not precede the first page")
        return self


class SourcePassage(BaseModel):
    id: str
    session_id: str
    revision: int
    page_label: str
    side: Literal["left", "right"]
    text: str
    page_number: int | None = None
    kind: Literal["original", "summary"] = "original"
    original_source_ids: list[str] = Field(default_factory=list)


class AnswerCitation(BaseModel):
    source_id: str
    quote: str = Field(min_length=1, max_length=1500)


class BookAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=12000)
    supported: bool
    citations: list[AnswerCitation] = Field(max_length=8)


class TurnResponse(BaseModel):
    id: str
    thread_id: str
    question: str
    status: Literal["pending", "queued", "generating", "complete", "failed"]
    error: str | None
    answer: BookAnswer | None
    sources: list[SourcePassage]
    source_count: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    created_at: str
    retrieval_strategy: str | None = None
    retrieval_notes: list[str] = Field(default_factory=list)


class ThreadDetail(ThreadResponse):
    turns: list[TurnResponse]
