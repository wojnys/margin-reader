from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConversationExample(BaseModel):
    example_en: str = Field(min_length=1, max_length=1000)
    example_cs: str = Field(min_length=1, max_length=1000)


class GeneratedConversationCard(BaseModel):
    source_index: int = Field(ge=0, le=21)
    meaning_cs: str = Field(min_length=1, max_length=1000)
    explanation_cs: str = Field(min_length=1, max_length=2000)
    pattern_cs: str = Field(min_length=1, max_length=1000)
    register_cs: str = Field(min_length=1, max_length=1000)
    work: ConversationExample
    social: ConversationExample
    errands: ConversationExample


class GeneratedConversation(BaseModel):
    cards: list[GeneratedConversationCard] = Field(min_length=1, max_length=3)


class ConversationCard(GeneratedConversationCard):
    expression: str
    source_sentence: str
    page_side: Literal["left", "right"]


class ConversationResponse(BaseModel):
    status: Literal["pending", "queued", "generating", "complete", "failed"]
    error: str | None
    cards: list[ConversationCard]


class GenerateConversation(BaseModel):
    revision: int = Field(ge=1)
