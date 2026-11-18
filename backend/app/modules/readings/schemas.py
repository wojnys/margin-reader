from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.ai.schemas import ExtractedPages, Learning, Translation
from backend.app.modules.conversation.schemas import ConversationResponse


class UsageResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    estimated_cost: float


class ReadingResponse(BaseModel):
    id: str
    book_id: str
    page_label: str
    batch_id: str | None = None
    batch_position: int | None = None
    status: str
    error: str | None
    revision: int
    created_at: str
    extraction: ExtractedPages | None
    translation: Translation | None
    learning: Learning | None
    conversation: ConversationResponse | None = None
    saved_expressions: list[str]
    is_sample: bool
    usage: UsageResponse


class SampleResponse(BaseModel):
    book_id: str
    session_id: str


class RefreshLearning(BaseModel):
    revision: int = Field(ge=1)


class CorrectText(BaseModel):
    revision: int = Field(ge=1)
    left: str = Field(min_length=1, max_length=30000)
    right: str = Field(min_length=1, max_length=30000)
