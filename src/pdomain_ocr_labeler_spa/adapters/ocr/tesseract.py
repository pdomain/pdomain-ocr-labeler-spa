from __future__ import annotations

import asyncio
import csv
import io
import os
import shutil
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from pdomain_book_contracts.geometry.bounding_box import BoundingBox
from pdomain_book_contracts.geometry.point import Point
from pdomain_book_tools.ocr.block import Block, BlockCategory, BlockChildType
from pdomain_book_tools.ocr.page import Page
from pdomain_book_tools.ocr.word import Word
from PIL import Image

from ...core.page_state import PageImageNotFoundError, PageLoadOutcome, PageSource
from .base import OCRProvenance
from .local_doctr import LocalDoctrPageLoader, _ingest_ocr_result

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from contextlib import AbstractContextManager

    from pdomain_book_contracts.annotation import PageKind

    from ...core.models import Project
    from ...core.persistence.page_store import LabelerPageStore


class TesseractCapabilityError(RuntimeError):
    """The configured CPU OCR engine cannot run on this host."""


class OCRCancelledError(RuntimeError):
    """OCR was cancelled before its result could be persisted."""


@dataclass(frozen=True)
class TesseractCapability:
    """Installed Tesseract executable and requested language availability."""

    available: bool
    binary: str | None
    language: str
    version: str
    languages: tuple[str, ...]
    message: str


async def _execute(
    arguments: Sequence[str],
    *,
    image_bytes: bytes | None = None,
    timeout_s: float,
    cancelled: Callable[[], bool] | None = None,
) -> str:
    if cancelled is not None and cancelled():
        raise OCRCancelledError("Tesseract OCR cancelled")
    environment = dict(os.environ, OMP_THREAD_LIMIT="1")
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdin=asyncio.subprocess.PIPE if image_bytes is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
    )
    communication = asyncio.create_task(process.communicate(image_bytes))
    deadline = time.monotonic() + timeout_s if timeout_s > 0 else None
    try:
        while not communication.done():
            if cancelled is not None and cancelled():
                raise OCRCancelledError("Tesseract OCR cancelled")
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"Tesseract OCR timed out after {timeout_s}s")
            await asyncio.wait({communication}, timeout=0.05)
        output, errors = await communication
        if process.returncode != 0:
            detail = errors.decode("utf-8", errors="replace")[:2000]
            raise TesseractCapabilityError(f"Tesseract exited with status {process.returncode}: {detail}")
        return output.decode("utf-8")
    finally:
        if process.returncode is None:
            process.kill()
        await communication


def tesseract_capability(
    *,
    binary: str = "tesseract",
    language: str = "eng",
    timeout_s: float = 5,
    cancelled: Callable[[], bool] | None = None,
) -> TesseractCapability:
    """Inspect the configured installed engine without selecting a fallback."""
    executable = shutil.which(binary)
    if executable is None:
        return TesseractCapability(False, None, language, "", (), f"Tesseract binary unavailable: {binary}")
    try:
        version = asyncio.run(
            _execute([executable, "--version"], timeout_s=timeout_s, cancelled=cancelled)
        ).splitlines()[0]
        language_output = asyncio.run(
            _execute([executable, "--list-langs"], timeout_s=timeout_s, cancelled=cancelled)
        )
    except (OSError, TimeoutError, TesseractCapabilityError) as exc:
        return TesseractCapability(False, executable, language, "", (), str(exc))
    languages = tuple(line.strip() for line in language_output.splitlines()[1:] if line.strip())
    if not language or any(part not in languages for part in language.split("+")):
        return TesseractCapability(
            False, executable, language, version, languages, f"Tesseract language unavailable: {language}"
        )
    return TesseractCapability(True, executable, language, version, languages, "Tesseract CPU OCR available")


def _box(row: dict[str | None, str | list[str] | None]) -> BoundingBox:
    values: list[int] = []
    for key in ("left", "top", "width", "height"):
        value = row.get(key)
        if not isinstance(value, str):
            raise ValueError(f"Invalid Tesseract TSV {key}")
        values.append(int(value))
    left, top, width, height = values
    if min(values) < 0:
        raise ValueError("Invalid Tesseract TSV geometry")
    return BoundingBox(Point(left, top), Point(left + width, top + height), is_normalized=False)


def _row_string(row: dict[str | None, str | list[str] | None], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Invalid Tesseract TSV {key}")
    return value


def parse_tesseract_tsv(tsv: str, *, width: int, height: int, page_index: int, name: str) -> Page:
    """Keep Tesseract blocks, paragraphs, lines and word geometry without reorganization."""
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    required = {
        "level",
        "page_num",
        "block_num",
        "par_num",
        "line_num",
        "word_num",
        "left",
        "top",
        "width",
        "height",
        "conf",
        "text",
    }
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("Invalid Tesseract TSV header")
    grouped: dict[tuple[int, int, int], list[Word]] = {}
    boxes: dict[tuple[int, ...], BoundingBox] = {}
    for row in reader:
        level = int(_row_string(row, "level"))
        block_id = int(_row_string(row, "block_num"))
        paragraph_id = int(_row_string(row, "par_num"))
        line_id = int(_row_string(row, "line_num"))
        if level in (2, 3, 4):
            key = (block_id, paragraph_id, line_id)[: level - 1]
            boxes[key] = _box(row)
        if level != 5:
            continue
        text = _row_string(row, "text")
        if not text.strip():
            continue
        confidence = float(_row_string(row, "conf"))
        word = Word(text, _box(row), ocr_confidence=confidence / 100 if confidence >= 0 else None)
        grouped.setdefault((block_id, paragraph_id, line_id), []).append(word)
    paragraphs: dict[tuple[int, int], list[Block]] = {}
    for (block_id, paragraph_id, line_id), words in grouped.items():
        line = Block(
            words,
            bounding_box=boxes.get((block_id, paragraph_id, line_id)),
            child_type=BlockChildType.WORDS,
            block_category=BlockCategory.LINE,
            additional_block_attributes={"tesseract_line": line_id},
        )
        paragraphs.setdefault((block_id, paragraph_id), []).append(line)
    blocks: dict[int, list[Block]] = {}
    for (block_id, paragraph_id), lines in paragraphs.items():
        paragraph = Block(
            lines,
            bounding_box=boxes.get((block_id, paragraph_id)),
            block_category=BlockCategory.PARAGRAPH,
            additional_block_attributes={"tesseract_paragraph": paragraph_id},
        )
        blocks.setdefault(block_id, []).append(paragraph)
    page_blocks = [
        Block(
            children,
            bounding_box=boxes.get((block_id,)),
            override_page_sort_order=order,
            additional_block_attributes={"tesseract_block": block_id},
        )
        for order, (block_id, children) in enumerate(blocks.items())
    ]
    return Page(width=width, height=height, page_index=page_index, blocks=page_blocks, name=name)


def _recognize(
    image_bytes: bytes,
    *,
    page_index: int,
    name: str,
    binary: str,
    language: str,
    timeout_s: float,
    cancelled: Callable[[], bool] | None,
) -> Page:
    started = time.monotonic()
    capability = tesseract_capability(
        binary=binary,
        language=language,
        timeout_s=min(timeout_s, 5) if timeout_s > 0 else 5,
        cancelled=cancelled,
    )
    if not capability.available or capability.binary is None:
        raise TesseractCapabilityError(capability.message)
    with Image.open(io.BytesIO(image_bytes)) as image:
        width, height = image.size
    remaining = timeout_s - (time.monotonic() - started) if timeout_s > 0 else 0
    if timeout_s > 0 and remaining <= 0:
        raise TimeoutError(f"Tesseract OCR timed out after {timeout_s}s")
    tsv = asyncio.run(
        _execute(
            [capability.binary, "stdin", "stdout", "-l", language, "--psm", "3", "tsv"],
            image_bytes=image_bytes,
            timeout_s=remaining,
            cancelled=cancelled,
        )
    )
    page = parse_tesseract_tsv(tsv, width=width, height=height, page_index=page_index, name=name)
    image_array = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image_array is None:
        raise ValueError("Tesseract source image could not be decoded")
    page.cv2_numpy_page_image = image_array
    return page


@dataclass
class TesseractPageLoader:
    """CPU OCR at the live PageLoader boundary with existing durable page reload."""

    project: Project
    binary: str = "tesseract"
    language: str = "eng"
    timeout_s: float = 120
    store: LabelerPageStore | None = None
    image_path_resolver: Callable[[int], Path] | None = None
    cancelled: Callable[[], bool] | None = None
    commit_guard: Callable[[], AbstractContextManager[None]] | None = None

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        """Reuse the engine-independent event-store read path."""
        from ...core.ocr.predictor import PredictorCache

        loader = LocalDoctrPageLoader(
            self.project, PredictorCache(), "stock", "stock", None, store=self.store
        )
        return loader.load_labeled(page_index)

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        """The cache lane is retired; saved results use the event store."""
        return None

    def run_ocr(
        self, page_index: int, *, edited_image_bytes: bytes | None = None, page_kind: PageKind | None = None
    ) -> PageLoadOutcome:
        """OCR the verified image bytes and persist only a successful, uncancelled result."""
        started = time.monotonic()
        if self.cancelled is not None and self.cancelled():
            raise OCRCancelledError("Tesseract OCR cancelled")
        if not shutil.which(self.binary):
            raise TesseractCapabilityError(f"Tesseract binary unavailable: {self.binary}")
        if page_index < 0 or page_index >= len(self.project.image_paths):
            raise IndexError(f"page_index {page_index} out of range")
        path = (
            self.image_path_resolver(page_index)
            if self.image_path_resolver
            else self.project.image_paths[page_index]
        )
        if edited_image_bytes is None:
            try:
                image_bytes = path.read_bytes()
            except FileNotFoundError as exc:
                raise PageImageNotFoundError(f"Page image not found: {path}") from exc
        else:
            image_bytes = edited_image_bytes
        page = _recognize(
            image_bytes,
            page_index=page_index,
            name=self.project.image_paths[page_index].name,
            binary=self.binary,
            language=self.language,
            timeout_s=self.timeout_s,
            cancelled=self.cancelled,
        )
        page.page_kind = page_kind
        with self.commit_guard() if self.commit_guard is not None else nullcontext():
            if self.cancelled is not None and self.cancelled():
                raise OCRCancelledError("Tesseract OCR cancelled")
            if self.timeout_s > 0 and time.monotonic() - started >= self.timeout_s:
                raise TimeoutError(f"Tesseract OCR timed out after {self.timeout_s}s")
            if self.store is not None:
                aggregate = _ingest_ocr_result(
                    page=page,
                    image_bytes=image_bytes,
                    page_index=page_index,
                    store=self.store,
                    project=self.project,
                    image_is_edited=edited_image_bytes is not None,
                    tool="tesseract",
                )
                object.__setattr__(page, "_labeler_page_id", aggregate.record.page_id)
        return PageLoadOutcome(page_index=page_index, source=PageSource.OCR, payload=page)


@dataclass
class TesseractOCR:
    """Expose the same installed CPU provider through the auxiliary engine protocol."""

    binary: str = "tesseract"
    language: str = "eng"
    timeout_s: float = 120

    async def ocr_page(
        self, image: object, *, detection_key: str, recognition_key: str, hf_revision: str | None
    ) -> tuple[Page, OCRProvenance]:
        """Recognize an encoded image or the protocol's BGR image array."""
        if isinstance(image, bytes):
            image_bytes = image
        elif isinstance(image, np.ndarray):
            success, encoded = cv2.imencode(".png", image)
            if not success:
                raise ValueError("Tesseract source image could not be encoded")
            image_bytes = encoded.tobytes()
        else:
            raise TypeError("TesseractOCR.ocr_page requires encoded bytes or a BGR image array")
        page = await asyncio.to_thread(
            _recognize,
            image_bytes,
            page_index=0,
            name="image",
            binary=self.binary,
            language=self.language,
            timeout_s=self.timeout_s,
            cancelled=None,
        )
        return page, OCRProvenance(
            engine="tesseract", detection_key="psm3", recognition_key=self.language, hf_revision=None
        )
