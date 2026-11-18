from __future__ import annotations

import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.app.core.exceptions import DomainError


def normalized_image(content: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Unsupported format")
                if image.width * image.height > 60_000_000 or min(image.size) < 200:
                    raise ValueError("Image resolution out of bounds")
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((3600, 3600))
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=93)  # Drops EXIF/location metadata.
                return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise DomainError(
            422,
            "Use a readable JPEG, PNG, or WebP photograph (at least 200px per side; at most 60 megapixels). Convert HEIC to JPEG first.",
        ) from None
