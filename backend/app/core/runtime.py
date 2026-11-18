from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from backend.app.core.config import Settings
from backend.app.db.session import SessionFactory


@dataclass(frozen=True)
class Runtime:
    config: Settings
    sessions: SessionFactory
    owner_secret: str


class RuntimeApp(FastAPI):
    runtime: Runtime | None = None
