from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache

import tiktoken
from llama_index.core.node_parser import SentenceSplitter

from backend.app.ai.schemas import ExtractedPages
from backend.app.modules.readings.models import ReadingSession


def content_hash(reading: ReadingSession) -> str:
    pages = ExtractedPages.model_validate(reading.extraction)
    value = json.dumps([pages.left, pages.right, reading.page_label], ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def page_numbers(label: str) -> tuple[int | None, int | None]:
    match = re.fullmatch(r"\s*(?:Pages?\s+)?(\d+)\s*[-–—]\s*(\d+)\s*", label, re.I)
    if match:
        return int(match[1]), int(match[2])
    return None, None


@lru_cache(maxsize=1)
def splitter() -> SentenceSplitter:
    return SentenceSplitter(chunk_size=400, chunk_overlap=50)


def chunks(text: str) -> list[tuple[int, int, str]]:
    result: list[tuple[int, int, str]] = []
    start = 0
    for value in splitter().split_text(text):
        position = text.find(value, start)
        if position < 0:
            # A splitter must never silently rewrite evidence.
            raise ValueError("Passage splitter changed source text")
        result.append((position, position + len(value), value))
        start = position + 1
    return result


def tokens(text: str) -> int:
    return len(tokenizer().encode(text, disallowed_special=()))


@lru_cache(maxsize=1)
def tokenizer() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")
