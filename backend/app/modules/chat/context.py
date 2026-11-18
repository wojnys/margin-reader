"""Bounded context assembled from original, revision-tagged page text."""

from __future__ import annotations

import re

from backend.app.ai.schemas import ExtractedPages
from backend.app.modules.chat.schemas import SourcePassage
from backend.app.modules.readings.models import ReadingSession


def passages(readings: list[ReadingSession]) -> list[SourcePassage]:
    result: list[SourcePassage] = []
    for reading in readings:
        pages = ExtractedPages.model_validate(reading.extraction)
        for side in ("left", "right"):
            text = pages.left if side == "left" else pages.right
            offset, index = 0, 0
            while offset < len(text):
                end = min(offset + 1800, len(text))
                if end < len(text):
                    boundary = text.rfind(" ", offset + 900, end)
                    if boundary > offset:
                        end = boundary
                chunk = text[offset:end].strip()
                if chunk:
                    result.append(
                        SourcePassage(
                            id=f"{reading.id}:v{reading.revision}:{side}:{index}",
                            session_id=reading.id,
                            revision=reading.revision,
                            page_label=reading.page_label,
                            side=side,
                            text=chunk,
                        )
                    )
                offset, index = end, index + 1
    return result


def select_context(sources: list[SourcePassage], question: str) -> list[SourcePassage]:
    if sum(len(source.text) for source in sources) <= 64000:
        return sources
    # Every uploaded page is searched; only a bounded set enters a long-book request.
    # Include evenly distributed passages so broad recap requests retain book coverage.
    terms = {match.group() for match in re.finditer(r"[^\W_]{3,}", question.lower())} - {
        "the",
        "and",
        "this",
        "that",
        "what",
        "these",
        "book",
        "pages",
        "explain",
    }
    ranked = sorted(
        range(len(sources)),
        key=lambda i: sum(min(sources[i].text.lower().count(term), 5) for term in terms),
        reverse=True,
    )
    chosen = set(ranked[:18])
    chosen.update(round(i * (len(sources) - 1) / 5) for i in range(6))
    return [source for index, source in enumerate(sources) if index in chosen]
