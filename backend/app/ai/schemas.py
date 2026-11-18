from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ExtractedPages(BaseModel):
    left: str = Field(max_length=30000)
    right: str = Field(max_length=30000)
    readable: bool
    warnings: list[str] = Field(default_factory=list, max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)


class Translation(BaseModel):
    left_cs: str = Field(min_length=1, max_length=60000)
    right_cs: str = Field(min_length=1, max_length=60000)


class Expression(BaseModel):
    expression: str = Field(min_length=1, max_length=300)
    meaning_cs: str = Field(min_length=1, max_length=2000)
    explanation_cs: str = Field(min_length=1, max_length=3000)
    source_sentence: str = Field(min_length=1, max_length=4000)
    page_side: Literal["left", "right"]
    example_en: str = Field(min_length=1, max_length=2000)
    example_cs: str = Field(min_length=1, max_length=2000)
    kind: Literal["phrase", "phrasal verb", "collocation", "word"]
    level: Literal["B1", "B2", "C1"]


class ComprehensionCard(BaseModel):
    question_en: str = Field(min_length=1, max_length=2000)
    answer_cs: str = Field(min_length=1, max_length=4000)
    evidence_en: str = Field(min_length=1, max_length=4000)


class Learning(BaseModel):
    topic_title: str | None = Field(default=None, min_length=1, max_length=100)
    # Kept optional so readings saved by the former Czech-translation workflow still load.
    summary_cs: str | None = Field(default=None, min_length=1, max_length=6000)
    left_summary_en: str | None = Field(default=None, min_length=1, max_length=6000)
    right_summary_en: str | None = Field(default=None, min_length=1, max_length=6000)
    # Previously saved readings and the prepared tutorial can contain fewer items.
    expressions: list[Expression] = Field(min_length=1, max_length=22)
    questions: list[ComprehensionCard] = Field(min_length=1, max_length=4)


class GeneratedLearning(Learning):
    left_summary_en: str | None = Field(default=None, min_length=1, max_length=6000)
    right_summary_en: str | None = Field(default=None, min_length=1, max_length=6000)
    expressions: list[Expression] = Field(min_length=10, max_length=22)

    @model_validator(mode="after")
    def require_page_summaries(self) -> GeneratedLearning:
        if not self.left_summary_en or not self.right_summary_en:
            raise ValueError("Both page summaries are required")
        if not self.topic_title:
            raise ValueError("A short English topic title is required")
        return self
