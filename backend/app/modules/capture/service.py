from __future__ import annotations

import hashlib
import secrets
import socket
from datetime import timedelta

from fastapi import UploadFile

from backend.app.core.config import Settings
from backend.app.core.exceptions import DomainError
from backend.app.db.base import now, uid
from backend.app.db.session import UnitOfWork
from backend.app.modules.capture.models import Pairing
from backend.app.modules.capture.repository import CaptureRepository
from backend.app.modules.capture.schemas import BatchCaptureResponse, CaptureResponse, PairingResponse
from backend.app.modules.readings.models import ReadingSession
from backend.app.modules.readings.service import ReadingService

MAX_BATCH_IMAGES = 10
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_BATCH_BYTES = 80 * 1024 * 1024


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            address: tuple[str, int] = sock.getsockname()  # pyright: ignore[reportAny] -- typeshed leaves socket addresses untyped
            return address[0]
    except OSError:
        return "127.0.0.1"


class CaptureService:
    def __init__(self, uow: UnitOfWork, config: Settings) -> None:
        self.uow = uow
        self.config = config
        self.repository = CaptureRepository(uow.session)
        self.readings = ReadingService(uow, config)

    def pair(self, book_id: str, port: int) -> PairingResponse:
        self.readings.books.require(book_id)
        token = secrets.token_urlsafe(32)
        expiry = now() + timedelta(minutes=15)
        self.repository.add(
            Pairing(token_hash=hashlib.sha256(token.encode()).hexdigest(), book_id=book_id, expires_at=expiry)
        )
        base = self.config.phone_base_url.rstrip("/") or f"http://{lan_ip()}:{port}"
        self.uow.commit()
        return PairingResponse(url=f"{base}/capture/{token}", expires_at=expiry.isoformat() + "Z")

    def require(self, token: str) -> Pairing:
        if len(token) > 100:
            raise DomainError(404, "Upload link not found")
        pairing = self.repository.get(hashlib.sha256(token.encode()).hexdigest())
        if pairing is None or pairing.expires_at < now():
            raise DomainError(410, "This upload link has expired. Create a new one on your computer.")
        return pairing

    def info(self, token: str) -> CaptureResponse:
        pairing = self.require(token)
        return CaptureResponse(
            book_title=self.readings.books.require(pairing.book_id).title, used=pairing.used
        )

    async def upload(self, token: str, content: bytes, page_label: str) -> None:
        pairing = self.require(token)
        if pairing.used:
            raise DomainError(
                409, "This link has already received a photograph. Create a new link for the next spread."
            )
        reading = await self.readings.prepare_upload(pairing.book_id, content, page_label)
        try:
            if not self.repository.claim(pairing.token_hash, reading.id):
                raise DomainError(409, "This link has already been used")
            self.uow.commit()
        except BaseException:
            self.uow.rollback()
            self.readings.remove_upload(reading)
            raise

    async def upload_batch(
        self, token: str, images: list[UploadFile], page_labels: list[str]
    ) -> BatchCaptureResponse:
        pairing = self.require(token)
        if pairing.used:
            raise DomainError(409, "This link has already been used. Create a new link for another batch.")
        if not 1 <= len(images) <= MAX_BATCH_IMAGES:
            raise DomainError(422, "Choose between 1 and 10 photographs")
        if len(page_labels) != len(images) or any(len(label) > 100 for label in page_labels):
            raise DomainError(422, "Provide one page label per photograph, at most 100 characters each")
        batch_id, timestamp = uid(), now()
        readings: list[ReadingSession] = []
        total_bytes = 0
        try:
            for index, (image, label) in enumerate(zip(images, page_labels, strict=True)):
                content = await image.read(MAX_IMAGE_BYTES + 1)
                if len(content) > MAX_IMAGE_BYTES:
                    raise DomainError(413, "Each photograph must be smaller than 20 MB")
                total_bytes += len(content)
                if total_bytes > MAX_BATCH_BYTES:
                    raise DomainError(413, "The batch must be smaller than 80 MB in total")
                reading = await self.readings.prepare_upload(
                    pairing.book_id,
                    content,
                    label,
                    context_snapshot=readings[0].context if readings else None,
                )
                readings.append(reading)
                reading.batch_id, reading.batch_position, reading.created_at = batch_id, index, timestamp
            if not self.repository.claim(pairing.token_hash, readings[0].id):
                raise DomainError(409, "This link has already been used")
            self.uow.commit()
        except BaseException:
            self.uow.rollback()
            for reading in readings:
                self.readings.remove_upload(reading)
            raise
        return BatchCaptureResponse(batch_id=batch_id, session_ids=[reading.id for reading in readings])
