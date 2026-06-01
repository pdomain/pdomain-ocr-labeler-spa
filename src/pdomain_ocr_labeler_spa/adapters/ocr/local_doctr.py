"""Local-DocTR OCR backend.

Spec: ``docs/architecture/02-backend.md §7`` (``local_doctr.py wraps
pdomain_book_tools.ocr.document.Document.from_image_ocr_via_doctr and a
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
  pdomain_book_tools entry point. ``load_labeled`` and ``load_cached``
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
from .base import OCRProvenance

logger = logging.getLogger(__name__)


def _write_cached_envelope_text(path: Path, text: str) -> None:
    """Module-level write helper. Lifted so tests can monkeypatch the
    write site without touching ``Path.write_text`` globally (legacy
    parity tests rely on a granular failure-injection seam).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ingest_ocr_result(
    *,
    page: Any,
    image_bytes: bytes,
    page_index: int,
    store: Any,  # LabelerPageStore — TYPE_CHECKING import avoids circular dep
) -> Any:  # PageAggregate
    """Fire OcrCompleted on a new PageAggregate and persist via LabelerPageStore.

    This is the new event-store write path replacing ``build_envelope``. Called
    from ``run_ocr`` when a ``LabelerPageStore`` is available. Falls back to
    the legacy envelope write when ``store`` is ``None``.

    Parameters
    ----------
    page:
        ``pdomain_book_tools.ocr.page.Page`` — must expose ``page_id`` (UUID)
        and ``to_dict() -> dict``.
    image_bytes:
        Raw PNG bytes for the full image. Written to BlobStore.
    page_index:
        0-based index within the project.
    store:
        The project's ``LabelerPageStore``.

    Returns
    -------
    PageAggregate
        The newly saved aggregate.
    """
    from uuid import UUID, uuid4

    from pdomain_ops.page_aggregate import PageAggregate
    from pdomain_ops.pages import PageRecord, ProvenanceGraph, ProvenanceNode

    page_id = page.page_id
    if not isinstance(page_id, UUID):
        page_id = uuid4()

    # Write image blob
    image_hash = store.blobs.write(image_bytes)

    # Write Page JSON blob
    page_json_bytes = json.dumps(page.to_dict()).encode("utf-8")
    content_hash = store.blobs.write(page_json_bytes)

    # Build a minimal provenance node
    prov_node = ProvenanceNode(
        id=str(page_id),
        source="ocr",
        tool="doctr",
        blob_refs=[content_hash, image_hash],
    )
    prov_graph = ProvenanceGraph(
        nodes={prov_node.id: prov_node},
        head_id=prov_node.id,
        history=[prov_node.id],
    )

    record = PageRecord(
        page_id=page_id,
        page_index=page_index,
        source="ocr",
        provenance=prov_graph,
    )

    agg = PageAggregate(record)
    agg.ocr_completed(
        provenance_node=prov_node,
        blob_refs=[content_hash, image_hash],
    )
    store.save_page(agg)
    return agg


if TYPE_CHECKING:
    from pdomain_book_tools.ocr.page import Page


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
    """``PageLoader`` impl that runs DocTR via pdomain_book_tools.

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
    payload is a ``pdomain_book_tools.ocr.page.Page`` (the live OCR result);
    ``load_labeled`` / ``load_cached`` payloads are
    ``UserPageEnvelope`` instances (the deserialised on-disk shape, NOT
    yet lifted to a ``Page``). The route layer (M3-proper
    ``api/pages.py::get_page``) is responsible for lifting
    ``envelope.payload.page`` (a ``dict``) into a ``Page`` via
    ``pdomain_book_tools.ocr.page.Page.from_dict``. This keeps the loader
    pdomain_book_tools-import-free on the labeled/cached lanes — important
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
        """STUB: labeled lane retired (M5b). Returns None — M8/M9 wires LabelerPageStore."""
        return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        """STUB: cached lane retired (M5b). Returns None — M8/M9 wires LabelerPageStore."""
        return None

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
        document_module = importlib.import_module("pdomain_book_tools.ocr.document")
        # pdomain-book-tools ≥0.17.1 returns (Document, rotation_degrees) as a
        # tuple; older versions returned Document directly. Unpack defensively.
        ocr_result = document_module.Document.from_image_ocr_via_doctr(
            image_path,
            source_identifier=image_path.name,
            predictor=predictor,
        )
        doc = ocr_result[0] if isinstance(ocr_result, tuple) else ocr_result
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
        # STUB: cached-lane envelope write retired (M5b). M9 uses LabelerPageStore.

        return PageLoadOutcome(
            page_index=page_index,
            source=PageSource.OCR,
            payload=page_obj,
        )

    # ── auto-cache-write helper ──────────────────────────────────────

    def _build_ocr_provenance(self) -> None:
        """STUB: EnvelopeOCRProvenance is retired (M5b). Provenance is in PageAggregate."""
        return

    def _write_cached_envelope(self, page_index: int, page_obj: Any) -> None:
        """STUB: cached-lane envelope write retired (M5b). No-op."""
        pass  # pragma: no cover


__all__ = [
    "LocalDoctrOCR",
    "LocalDoctrPageLoader",
]
