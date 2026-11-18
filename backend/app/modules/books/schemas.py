from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class BookResponse(BaseModel):
    id: str
    title: str
    author: str
    level: str
    notes: str
    session_count: int


class BookInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(default="", max_length=200)
    level: Literal["B1", "B2", "C1"] = "B2"
    notes: str = Field(default="", max_length=4000)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a book title")
        return value.strip()
