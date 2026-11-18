from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.app.modules.capture.models import Pairing


class CaptureRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, token_hash: str) -> Pairing | None:
        return self.db.get(Pairing, token_hash)

    def add(self, pairing: Pairing) -> None:
        self.db.add(pairing)
        self.db.flush()

    def claim(self, token_hash: str, reading_id: str) -> bool:
        result = self.db.execute(
            update(Pairing)
            .where(Pairing.token_hash == token_hash, Pairing.used.is_(False))
            .values(used=True, session_id=reading_id)
            .returning(Pairing.token_hash)
        )
        return result.scalar_one_or_none() is not None
