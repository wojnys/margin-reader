"""Local, provider-independent OCR for photographed book spreads."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import cast

from PIL import Image
from rapidocr import RapidOCR
from rapidocr.utils.output import RapidOCROutput

from backend.app.ai.schemas import ExtractedPages


class OcrError(Exception):
    """Raised when the local OCR engine cannot inspect a photograph."""


@lru_cache(maxsize=1)
def engine() -> RapidOCR:
    """Create the CPU OCR engine once per worker process, on first use."""
    return RapidOCR()


def recognised_text(image: Image.Image) -> tuple[str, float | None]:
    output = cast(RapidOCROutput, engine()(image))
    lines = [line.strip() for line in output.txts or () if line.strip()]
    scores = output.scores or ()
    confidence = sum(scores) / len(scores) if scores else None
    return "\n".join(lines), confidence


def extract_pages(path: Path) -> ExtractedPages:
    """OCR each half independently so left/right page order cannot interleave."""
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
            width, height = image.size
            if width < 100 or height < 100:
                raise OcrError("The photograph is too small to read")
            gutter = max(8, round(width * 0.02))
            midpoint = width // 2
            left, left_confidence = recognised_text(image.crop((0, 0, min(width, midpoint + gutter), height)))
            right, right_confidence = recognised_text(
                image.crop((max(0, midpoint - gutter), 0, width, height))
            )
    except OcrError:
        raise
    except Exception as exc:
        raise OcrError("The local OCR engine could not read this photograph") from exc

    confidences = [score for score in (left_confidence, right_confidence) if score is not None]
    confidence = sum(confidences) / len(confidences) if confidences else None
    warnings: list[str] = []
    if confidence is not None and confidence < 0.8:
        warnings.append(
            f"Local OCR confidence is {confidence:.0%}. Compare the transcription with the photograph before learning from it."
        )
    readable = bool(left and right) and (confidence is None or confidence >= 0.4)
    if not readable:
        warnings.append(
            "OCR could not confidently read both pages. Try a sharper, evenly lit photograph or correct the text yourself."
        )
    return ExtractedPages(
        left=left,
        right=right,
        readable=readable,
        warnings=warnings,
        confidence=confidence,
    )
