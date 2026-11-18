from __future__ import annotations

from pydantic import BaseModel, Field


class VocabularyResponse(BaseModel):
    id: str
    expression: str
    meaning_cs: str
    explanation_cs: str
    example_en: str
    example_cs: str
    kind: str
    level: str
    source_sentence: str
    book_title: str
    due_at: str
    repetitions: int


class SaveExpression(BaseModel):
    session_id: str
    revision: int = Field(ge=1)
    index: int = Field(ge=0, le=21)
