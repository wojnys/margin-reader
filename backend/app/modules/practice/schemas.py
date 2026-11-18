from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    rating: int = Field(ge=0, le=3)
