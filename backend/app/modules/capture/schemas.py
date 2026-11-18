from __future__ import annotations

from pydantic import BaseModel


class PairingResponse(BaseModel):
    url: str
    expires_at: str


class CaptureResponse(BaseModel):
    book_title: str
    used: bool


class BatchCaptureResponse(BaseModel):
    batch_id: str
    session_ids: list[str]
