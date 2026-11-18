from __future__ import annotations

from pydantic import BaseModel


class OkResponse(BaseModel):
    ok: bool = True


class ErrorResponse(BaseModel):
    detail: str


class SystemResponse(BaseModel):
    api_key_configured: bool
    model: str
    temporal_connected: bool


class ValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ValidationErrorResponse(BaseModel):
    detail: str | list[ValidationIssue]
