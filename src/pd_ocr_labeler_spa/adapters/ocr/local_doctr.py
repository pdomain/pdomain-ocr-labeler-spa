"""Local-DocTR OCR backend.

Spec: ``docs/architecture/02-backend.md §7`` (``local_doctr.py wraps
pd_book_tools.ocr.document.Document.from_image_ocr_via_doctr and a
predictor cache``) and ``specs/16-milestones.md`` M3.

Two seam classes:

- ``LocalDoctrOCR`` — implements ``IOCREngine``. Body still
  ``NotImplementedError`` at this slice; the SPA's primary OCR seam
  is the ``PageLoader`` protocol (which delivers a ``PageLoadOutcome``
  the page-state cache can consume directly), so the ``IOCREngine``
  surface stays unwired until either a Modal/SharedContainer backend
  lands or the route layer calls ``ocr_page`` directly. Distinct from
  ``NotImplementedYet`` (which marks "never wired in v1") — see B-46.
- ``LocalDoctrPageLoader`` — implements ``PageLoader`` from
  ``core/page_state``. ``run_ocr`` wires the predictor cache + the
  pd_book_tools entry point. ``load_labeled`` and ``load_cached``
  return ``None`` until ``core/persistence/user_page_envelope.py``
  ships (a separate M3 slice).

Legacy reference: ``pd-ocr-labeler/pd_ocr_labeler/operations/ocr/
page_operations.py:339-360`` (``_parse_page`` inside
``build_initial_page_parser``).
"""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...core.models import Project
from ...core.ocr.predictor import PredictorCache
from ...core.page_state import (
    PageImageNotFoundError,
    PageLoadOutcome,
    PageSource,
)
from ...core.persistence.ground_truth import find_ground_truth_text
from ...core.persistence.user_page_envelope import (
    USER_PAGE_SOURCE_LANE_CACHED,
    OCRModelProvenance,
    build_envelope,
    cached_envelope_path,
    envelope_to_dict,
    labeled_envelope_path,
    read_envelope_file,
)
from ...core.persistence.user_page_envelope import (
    OCRProvenance as EnvelopeOCRProvenance,
)
from .base import OCRProvenance

logger = logging.getLogger(__name__)


def _write_cached_envelope_text(path: Path, text: str) -> None:
    """Module-level write helper. Lifted so tests can monkeypatch the
    write site without touching ``Path.write_text`` globally (legacy
    parity tests rely on a granular failure-injection seam).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if TYPE_CHECKING:
    from pd_book_tools.ocr.page import Page


class LocalDoctrOCR:
    """Wrapper around DocTR; predictor-cached.

    Conformance to ``IOCREngine`` is purely structural (PEP 544); no
    explicit subclass — see ``adapters/__init__.py`` for the policy.
    (B-46.) Body intentionally unwired at M3; primary OCR seam is
    ``LocalDoctrPageLoader.run_ocr`` below.
    """

    async def ocr_page(
        self,
        image: Any,
        *,
        detection_key: str,
        recognition_key: str,
        hf_revision: str | None,
    ) -> tuple[Page, OCRProvenance]:
        raise NotImplementedError(
            "LocalDoctrOCR.ocr_page is unwired — use LocalDoctrPageLoader.run_ocr "
            "for in-process OCR runs (docs/architecture/02-backend.md §7)."
        )


@dataclass
class LocalDoctrPageLoader:
    """``PageLoader`` impl that runs DocTR via pd_book_tools.

    Constructed per OCR session — bound to one ``Project`` plus a
    chosen ``(detection_key, recognition_key, hf_revision)`` triple.
    The ``PredictorCache`` is shared across loaders / route handlers
    so successive page loads with the same models reuse the predictor.

    Slice 8b-iv contract:

    - ``run_ocr(page_index)`` returns a ``PageLoadOutcome(source=OCR,
      payload=Page)`` (slice 8b-ii).
    - ``load_labeled(page_index)`` reads the labeled-lane envelope from
      ``<data_root>/labeled-projects/<project_id>/<project_id>_
      <page:03d>.json``. Returns ``PageLoadOutcome(source=FILESYSTEM,
      payload=UserPageEnvelope)`` on hit, ``None`` on miss / corrupt
      file (so ``ensure_page_model`` falls through per spec §9).
    - ``load_cached(page_index)`` reads from ``<cache_root>/
      page-images/<project_id>_<page:03d>_envelope.json``. Returns
      ``PageLoadOutcome(source=CACHED_OCR, payload=UserPageEnvelope)``
      on hit, ``None`` otherwise.
    - When ``data_root`` / ``cache_root`` are ``None``, the
      corresponding lane is a no-op (returns ``None``). This preserves
      the slice-8b-ii constructor signature so callers wiring only OCR
      can keep the previous shape; the route layer that builds the
      loader passes the real Settings paths.

    **Payload divergence between lanes** (intentional): ``run_ocr``'s
    payload is a ``pd_book_tools.ocr.page.Page`` (the live OCR result);
    ``load_labeled`` / ``load_cached`` payloads are
    ``UserPageEnvelope`` instances (the deserialised on-disk shape, NOT
    yet lifted to a ``Page``). The route layer (M3-proper
    ``api/pages.py::get_page``) is responsible for lifting
    ``envelope.payload.page`` (a ``dict``) into a ``Page`` via
    ``pd_book_tools.ocr.page.Page.from_dict``. This keeps the loader
    pd_book_tools-import-free on the labeled/cached lanes — important
    because reading a saved envelope must work even when DocTR isn't
    installed (B-46 IOCREngine vs PageLoader split).

    Failure modes:
    - ``run_ocr`` raises ``PageImageNotFoundError`` if the on-disk
      image is missing, ``IndexError`` if ``page_index`` is out of
      range. OCR engine errors propagate verbatim (page-state cache
      *does not* cache the failure — next call retries).
    - ``load_labeled`` / ``load_cached`` return ``None`` on ANY read
      failure (missing file, unparsable JSON, schema-name mismatch).
      Never raise — the dispatcher needs fall-through semantics.
    """

    project: Project
    predictor_cache: PredictorCache
    detection_key: str
    recognition_key: str
    hf_revision: str | None
    data_root: Path | None = None
    cache_root: Path | None = None

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        if self.data_root is None:
            return None
        path = labeled_envelope_path(self.data_root, self.project.project_id, page_index)
        envelope = read_envelope_file(path)
        if envelope is None:
            return None
        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.FILESYSTEM,
            payload=envelope,
        )

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        if self.cache_root is None:
            return None
        path = cached_envelope_path(self.cache_root, self.project.project_id, page_index)
        envelope = read_envelope_file(path)
        if envelope is None:
            return None
        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.CACHED_OCR,
            payload=envelope,
        )

    def run_ocr(self, page_index: int) -> PageLoadOutcome:
        if page_index < 0 or page_index >= len(self.project.image_paths):
            raise IndexError(
                f"page_index {page_index} out of range (total_pages={len(self.project.image_paths)})"
            )
        image_path = self.project.image_paths[page_index]
        if not image_path.exists():
            raise PageImageNotFoundError(f"Page image not found on disk: {image_path}")

        predictor = self.predictor_cache.get_or_create(
            self.detection_key, self.recognition_key, self.hf_revision
        )

        # Lazy import — keeps test collection torch-free; matches the
        # pattern in core/ocr/predictor._build.
        document_module = importlib.import_module("pd_book_tools.ocr.document")
        doc = document_module.Document.from_image_ocr_via_doctr(
            image_path,
            source_identifier=image_path.name,
            predictor=predictor,
        )
        # Legacy parity (ocr_service.py:80, page_operations.py:351):
        # ``Document`` produced from a single image has exactly one
        # ``Page`` at ``pages[0]``.
        page_obj: Page = doc.pages[0]

        # Ground-truth injection (legacy parity:
        # pd-ocr-labeler/operations/ocr/page_operations.py:363-364 +
        # state/project_state.py:709-719). Look up GT for the image
        # filename from project.ground_truth_map; if non-empty, call
        # page.add_ground_truth(gt_text). Skip on None / "" per
        # legacy ``if ground_truth_string:``. Done BEFORE the auto-
        # cache-write so the cached envelope captures the GT-augmented
        # page (matches legacy ordering: gt is injected inside the
        # page parser before the auto-save block in project_state.py).
        gt_text = find_ground_truth_text(image_path.name, self.project.ground_truth_map)
        if gt_text:
            try:
                page_obj.add_ground_truth(gt_text)
            except Exception as exc:  # pragma: no cover - defensive
                # Legacy doesn't guard this call, but a defensive
                # try/except keeps a malformed GT from breaking the
                # OCR result. Log and continue.
                logger.warning(
                    "GT injection failed for index=%s name=%s: %s",
                    page_index,
                    image_path.name,
                    exc,
                )

        # Auto-cache-write side effect (legacy parity:
        # pd-ocr-labeler/state/project_state.py:752-799). After a
        # successful OCR run, persist the cached envelope so subsequent
        # loads hit the cached lane instead of paying OCR cost again.
        # No-op when ``cache_root is None`` (preserves slice-8b-ii ctor
        # signature for OCR-only callers). Failures are
        # log-and-swallowed (legacy lines 789-794): a write failure
        # must not turn a successful OCR into a 5xx — the in-memory
        # outcome is still returned to the caller.
        if self.cache_root is not None:
            self._write_cached_envelope(page_index, page_obj)

        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.OCR,
            payload=page_obj,
        )

    # ── auto-cache-write helper ──────────────────────────────────────

    def _build_ocr_provenance(self) -> EnvelopeOCRProvenance:
        """Compose ``OCRProvenance`` from the loader's selected models.

        Legacy parity: ``page_operations._resolve_ocr_provenance_for_save``
        (line 1166). Records the detection + recognition keys + HF
        revision so a re-read of the cached envelope can identify the
        models that produced it.
        """
        models: list[OCRModelProvenance] = [
            OCRModelProvenance(
                name=self.detection_key,
                version=self.hf_revision,
            ),
            OCRModelProvenance(
                name=self.recognition_key,
                version=self.hf_revision,
            ),
        ]
        return EnvelopeOCRProvenance(engine="doctr", models=models)

    def _write_cached_envelope(self, page_index: int, page_obj: Any) -> None:
        """Side-effect: write the cached-lane envelope JSON.

        Failures log-and-swallow per legacy
        ``project_state.py:789-794``. Distinct from the labeled lane:
        cached writes use ``source_lane="cached"`` (slice 8b-v
        override) and land at ``cached_envelope_path(...)`` — the
        ``_envelope.json`` suffix avoids collision with legacy's plain
        ``.json`` writes to the shared cache dir.
        """
        if self.cache_root is None:  # caller-checked; explicit raise survives -O
            raise RuntimeError(
                "_write_cached_envelope called with cache_root=None — caller contract violated"
            )
        try:
            envelope = build_envelope(
                page=page_obj,
                project=self.project,
                page_index=page_index,
                ocr_provenance=self._build_ocr_provenance(),
                source_lane=USER_PAGE_SOURCE_LANE_CACHED,
            )
            target = cached_envelope_path(self.cache_root, self.project.project_id, page_index)
            _write_cached_envelope_text(target, json.dumps(envelope_to_dict(envelope), ensure_ascii=False))
            logger.debug(
                "auto-cache-write: wrote cached envelope index=%s path=%s",
                page_index,
                target,
            )
        except Exception as exc:  # pragma: no cover - exercised via injection
            logger.debug(
                "auto-cache-write: failed for index=%s: %s",
                page_index,
                exc,
            )


__all__ = [
    "LocalDoctrOCR",
    "LocalDoctrPageLoader",
]
