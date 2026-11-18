from __future__ import annotations

import threading
from functools import lru_cache
from typing import Protocol, cast


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class LocalEmbedder:
    def __init__(self, name: str) -> None:
        # Lazy import/download: schema export and ordinary API imports remain offline.
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(name, token=False)
        self.lock = threading.Lock()

    def encode(self, texts: list[str]) -> list[list[float]]:
        with self.lock:
            result = cast(list[list[float]], self.model.encode(texts, normalize_embeddings=True).tolist())  # pyright: ignore[reportUnknownMemberType] -- third-party overload includes unsupported multimodal types
        if any(len(row) != 1024 for row in result):
            raise ValueError(
                "Knowledge embeddings require a 1024-dimensional model; changing models requires a new index"
            )
        return result


@lru_cache(maxsize=2)
def embedder(name: str) -> Embedder:
    return LocalEmbedder(name)
