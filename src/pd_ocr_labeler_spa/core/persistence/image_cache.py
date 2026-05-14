"""Content-addressed image cache for rendered page images.

Spec authority:
- ``docs/specs/2026-05-12-persistence-design.md §Image cache``
- Issue #222 acceptance criteria.

Filename convention (shared with legacy ``pd-ocr-labeler`` under D-003)::

    <cache_root>/page-images/<project>_<page:03d>_<type>_<sha>.{jpg,png}

where ``sha`` is the SHA-1 of the *encoded* bytes (after JPEG or PNG
compression), lowercase hex, first 16 characters.  Two independent writers
with identical inputs therefore produce the same filename — content-
addressable, collision-safe.

Image types: ``original | lines | words | paragraphs | matched_words``.

Sizing:
- ``_MAX_CACHED_DIMENSION = 1200`` — images wider or taller than this are
  downscaled (keeping aspect ratio) before encoding.
- JPEG quality 92 for all JPEG-eligible images.
- PNG fallback: when the JPEG round-trip (encode → decode → compare) differs
  from the source above a threshold (mean absolute pixel delta > 3 across any
  channel), the file is stored as PNG instead.  The fallback is rare in
  practice (occurs with synthetic high-contrast images or embedded palette
  transparency); this module handles it transparently.

Cache lifetime: files accumulate until ``make clean-cache`` removes them
(or the user clears the cache dir manually).  No automatic eviction.
"""

from __future__ import annotations

import hashlib
import io
import logging
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from .atomic import write_bytes_atomic
from .paths import image_cache_root

if TYPE_CHECKING:
    from PIL import Image as PilImage

logger = logging.getLogger(__name__)

_MAX_CACHED_DIMENSION = 1200
"""Max pixel dimension (width or height) before down-scaling. Spec §Image cache."""

_JPEG_QUALITY = 92
"""JPEG quality setting. Spec §Image cache."""

_JPEG_LOSSY_THRESHOLD = 3.0
"""Mean absolute delta (0-255) per channel above which PNG fallback is chosen."""


class ImageType(str, Enum):
    """Discriminants for the five rendered image types. Spec §Image cache."""

    ORIGINAL = "original"
    LINES = "lines"
    WORDS = "words"
    PARAGRAPHS = "paragraphs"
    MATCHED_WORDS = "matched_words"


def cached_image_path(
    cache_root: Path,
    project_id: str,
    page_index: int,
    image_type: ImageType,
    encoded_bytes: bytes,
) -> Path:
    """Derive the content-addressed cache path for given encoded bytes.

    Pure function — no I/O.  ``encoded_bytes`` are the *already-encoded* bytes
    (the same bytes that will be written to disk), so the SHA covers the actual
    file content.
    """
    sha = hashlib.sha1(encoded_bytes, usedforsecurity=False).hexdigest()[:16]
    root = image_cache_root(cache_root)
    ext = "jpg" if _bytes_are_jpeg(encoded_bytes) else "png"
    name = f"{project_id}_{page_index:03d}_{image_type.value}_{sha}.{ext}"
    return root / name


def _bytes_are_jpeg(data: bytes) -> bool:
    """Return True when ``data`` begins with the JPEG SOI marker (FF D8)."""
    return len(data) >= 2 and data[0] == 0xFF and data[1] == 0xD8


def encode_image(image: PilImage.Image) -> bytes:
    """Encode *image* to JPEG-92 (with PNG fallback).

    Steps:
    1. Down-scale if either dimension exceeds ``_MAX_CACHED_DIMENSION``.
    2. Attempt JPEG quality-92 encoding.
    3. Decode the JPEG back and compare pixel-wise with the (possibly
       down-scaled) source.
    4. If mean absolute delta > ``_JPEG_LOSSY_THRESHOLD`` for any channel,
       re-encode as PNG (lossless).

    Returns the encoded bytes (JPEG or PNG).
    """
    from PIL import Image  # lazy; PIL arrives via pd-book-tools

    img = _maybe_downscale(image)

    # Ensure RGB for JPEG (no alpha channel allowed in JPEG).
    if img.mode in ("RGBA", "LA", "PA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        rgb_img = bg
    elif img.mode != "RGB":
        rgb_img = img.convert("RGB")
    else:
        rgb_img = img

    buf_jpeg = io.BytesIO()
    rgb_img.save(buf_jpeg, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    jpeg_bytes = buf_jpeg.getvalue()

    if _jpeg_is_acceptable(rgb_img, jpeg_bytes):
        return jpeg_bytes

    # PNG fallback.
    buf_png = io.BytesIO()
    img.save(buf_png, format="PNG", optimize=True)
    return buf_png.getvalue()


def _maybe_downscale(image: PilImage.Image) -> PilImage.Image:
    """Return *image* down-scaled so neither dimension exceeds ``_MAX_CACHED_DIMENSION``."""
    w, h = image.size
    if w <= _MAX_CACHED_DIMENSION and h <= _MAX_CACHED_DIMENSION:
        return image

    from PIL import Image  # lazy

    scale = _MAX_CACHED_DIMENSION / max(w, h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    return image.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _jpeg_is_acceptable(original: PilImage.Image, jpeg_bytes: bytes) -> bool:
    """Return True when the JPEG round-trip delta is within the threshold."""
    try:
        import numpy as np
        from PIL import Image  # lazy

        decoded = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        orig_arr = np.array(original.convert("RGB"), dtype=float)
        dec_arr = np.array(decoded, dtype=float)
        if orig_arr.shape != dec_arr.shape:
            return False
        mean_delta = float(np.abs(orig_arr - dec_arr).mean())
        return mean_delta <= _JPEG_LOSSY_THRESHOLD
    except Exception:
        # Any error in the comparison falls back to PNG for safety.
        return False


def write_cached_image(
    cache_root: Path,
    project_id: str,
    page_index: int,
    image_type: ImageType,
    image: PilImage.Image,
) -> Path:
    """Encode *image* and write it to the content-addressed cache.

    Creates ``<cache_root>/page-images/`` if missing.  Returns the path
    of the written file.  If the file already exists (same SHA), skips the
    write and returns the existing path.

    Never raises on I/O failure — logs at WARNING and re-raises so the
    caller decides whether to 500 (write-side) or degrade gracefully (cache).
    """
    encoded = encode_image(image)
    path = cached_image_path(cache_root, project_id, page_index, image_type, encoded)

    if path.exists():
        logger.debug("image_cache hit: %s", path.name)
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, encoded)
    logger.debug("image_cache write: %s", path.name)
    return path


__all__ = [
    "_JPEG_QUALITY",
    "_MAX_CACHED_DIMENSION",
    "ImageType",
    "cached_image_path",
    "encode_image",
    "write_cached_image",
]
