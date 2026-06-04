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
import tempfile
import uuid
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


# Stable namespace for deriving a project's ``ProjectAggregate`` UUID from its
# string ``project_id``. The labeler keys a project by a human/string id
# (URLs, directories), but the ops ``ProjectAggregate`` is keyed by a UUID.
# ``uuid5(NAMESPACE, project_id)`` gives a deterministic, collision-free,
# restart-stable mapping with no persisted side-table — exactly what a
# name-based UUID is for. This is the canonical project-UUID resolution used by
# both the OCR write path (project registration) and the restart read path
# (``load_labeled``). Do not change this constant: it is the cross-restart
# identity anchor; changing it would orphan every previously-stored project.
_PROJECT_UUID_NAMESPACE = uuid.UUID("6f3c3d2a-1b4e-5a6c-8d7e-9f0a1b2c3d4e")

# Sentinel for a project index→page_id slot that is reserved but not yet OCR'd.
# When the user OCRs a higher page index before the lower ones exist, the gap
# slots are padded with this NIL uuid so the restart read path treats them as
# "not present" (returns None → falls through to run_ocr) rather than resolving
# them to some other page's real content. Replaced with the real page_id when
# that index is finally OCR'd.
_NIL_PAGE_ID = uuid.UUID(int=0)


def _project_uuid_for(project_id: str) -> uuid.UUID:
    """Map a labeler string ``project_id`` to its stable ``ProjectAggregate`` UUID.

    Deterministic across processes (``uuid5``) so a fresh process resolves the
    same project aggregate that the OCR write path created. No side-table.
    """
    return uuid.uuid5(_PROJECT_UUID_NAMESPACE, project_id)


def _register_page_in_project(
    *,
    store: Any,  # LabelerPageStore
    project_id: str,
    page_id: uuid.UUID,
    page_index: int,
) -> None:
    """Create-or-update the ProjectAggregate so ``page_ids[page_index] == page_id``.

    Builds the index→page_id map a fresh ``load_labeled`` needs. Idempotent:
    re-OCR of the same index replaces that slot rather than appending a
    duplicate, and the page-id list is padded as needed so ``page_index`` is a
    valid slot. When ``page_index`` is beyond the current end (a higher index
    OCR'd before the lower ones — non-sequential navigation), the intervening
    gap slots are padded with the NIL uuid (``_NIL_PAGE_ID``), never this page's
    real id, so the restart read path cannot resolve a gap index to the wrong
    page's content. Best-effort caller wraps this — a failure here must not turn
    a good OCR into a 5xx.
    """
    from eventsourcing.application import AggregateNotFoundError
    from pdomain_ops.page_aggregate import ProjectAggregate
    from pdomain_ops.pages import ProjectRecord

    proj_uuid = _project_uuid_for(project_id)
    try:
        proj_agg = store.get_project(proj_uuid)
    except AggregateNotFoundError:
        proj_agg = ProjectAggregate(ProjectRecord(project_id=proj_uuid, name=project_id))

    page_ids = list(proj_agg.record.page_ids)
    if page_index < len(page_ids):
        if page_ids[page_index] == page_id:
            return  # already registered at this slot — nothing to do
        page_ids[page_index] = page_id
        proj_agg.reorder_pages(page_ids)
    elif page_index == len(page_ids):
        proj_agg.add_page(page_id=page_id, page_index=page_index)
    else:
        # Sparse index: the user OCR'd a higher index before the intervening
        # ones exist (non-sequential navigation is allowed). Pad gap slots with
        # the NIL uuid — NOT this page's real id — so a later ``load_labeled``
        # of a gap index resolves to "not present" and falls through to run_ocr,
        # instead of handing back THIS page's content stamped at the wrong index.
        # reorder_pages replaces the whole ordering atomically.
        while len(page_ids) < page_index:
            page_ids.append(_NIL_PAGE_ID)
        page_ids.append(page_id)
        proj_agg.reorder_pages(page_ids)
    store.save_project(proj_agg)


def _ingest_ocr_result(
    *,
    page: Any,
    image_bytes: bytes,
    page_index: int,
    store: Any,  # LabelerPageStore — TYPE_CHECKING import avoids circular dep
    project: Any = None,  # Project — its project_id keys the ProjectAggregate
) -> Any:  # PageAggregate
    """Fire OcrCompleted on a new PageAggregate and persist via LabelerPageStore.

    This is the new event-store write path replacing ``build_envelope``. Called
    from ``run_ocr`` when a ``LabelerPageStore`` is available.

    When ``project`` is supplied, the page is ALSO registered into the project's
    ``ProjectAggregate`` (index→page_id map) so a fresh process can resolve which
    page_id sits at ``page_index`` on the restart read path (``load_labeled``).
    Registration is idempotent: re-OCR of the same index replaces the slot.

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
    project:
        The ``Project`` whose ``project_id`` keys the ``ProjectAggregate``. When
        ``None``, only the ``PageAggregate`` is written (no index→page_id map);
        the restart read path then cannot resolve this page.

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

    # Register into the project aggregate so the restart read path can resolve
    # page_index → page_id. Best-effort: a project-write failure must not lose
    # the (already-saved) page aggregate.
    if project is not None:
        try:
            _register_page_in_project(
                store=store,
                project_id=project.project_id,
                page_id=page_id,
                page_index=page_index,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "run_ocr: project-aggregate registration failed for page=%d: %s",
                page_index,
                exc,
            )

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

    **Lane payloads** (post event-store adoption): every lane that returns
    a payload returns a ``pdomain_book_tools.ocr.page.Page``. ``run_ocr`` returns
    the freshly-OCR'd page; ``load_labeled`` returns the page reconstructed from
    the event store (``Page.from_dict`` over the head content blob), which
    carries any persisted labeler edits because a save advances the aggregate's
    provenance head to the edited content blob. The reconstructed page is
    stamped with ``_labeler_page_id`` so the route layer can route subsequent
    mutations to the right aggregate.

    Failure modes:
    - ``run_ocr`` raises ``PageImageNotFoundError`` if the on-disk
      image is missing, ``IndexError`` if ``page_index`` is out of
      range. OCR engine errors propagate verbatim (page-state cache
      *does not* cache the failure — next call retries).
    - ``load_labeled`` / ``load_cached`` return ``None`` on ANY read
      failure (no store, no project aggregate, index out of range,
      missing/corrupt blob). Never raise — the dispatcher needs
      fall-through semantics so a miss falls through to ``run_ocr``.
    """

    project: Project
    predictor_cache: PredictorCache
    detection_key: str
    recognition_key: str
    hf_revision: str | None
    data_root: Path | None = None
    cache_root: Path | None = None
    store: Any = None  # LabelerPageStore | None — write OCR result to event store

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None:
        """Reload a stored page from the event store (the restart read path).

        Resolves the project's ``ProjectAggregate`` (keyed by the stable
        ``uuid5`` derived from ``project.project_id``), looks up the ``page_id``
        registered at ``page_index``, reads that page's head content blob, and
        reconstructs the ``Page``. The reconstructed ``Page`` carries the
        edits that were persisted via ``save_page_content_to_store`` because the
        labeler edit advances the aggregate's provenance head to the edited
        content blob.

        This is what makes labeler edits survive a process restart: a fresh
        process resolves the stored, edited content here instead of falling
        through to ``run_ocr`` (which would discard every edit).

        Returns
        -------
        PageLoadOutcome | None
            ``PageLoadOutcome(source=FILESYSTEM, payload=Page)`` on a hit, with
            ``_labeler_page_id`` stamped on the ``Page`` so subsequent mutations
            target the same aggregate. ``None`` on ANY failure or missing data
            (no store, no project aggregate, index out of range, missing/corrupt
            blob) — never raises, so ``ensure_page_model`` falls through to
            ``run_ocr`` cleanly.
        """
        if self.store is None:
            return None
        try:
            from ...api._page_content import load_page_from_store as _load_page_from_store

            proj_uuid = _project_uuid_for(self.project.project_id)
            proj_agg = self.store.get_project(proj_uuid)
            page_ids = proj_agg.record.page_ids
            if page_index < 0 or page_index >= len(page_ids):
                return None
            page_id = page_ids[page_index]
            if page_id == _NIL_PAGE_ID:
                # Reserved gap slot (a higher index was OCR'd first); this index
                # has no stored page yet — fall through to run_ocr.
                return None

            page_obj = _load_page_from_store(self.store, page_id)
            if page_obj is None:
                return None

            # Stamp the page_id so subsequent event-store mutations (saves,
            # refines) target this aggregate without a fresh lookup.
            object.__setattr__(page_obj, "_labeler_page_id", page_id)
            return PageLoadOutcome(
                page_index=page_index,
                source=PageSource.FILESYSTEM,
                payload=page_obj,
            )
        except Exception as exc:  # pragma: no cover - defensive fall-through
            logger.debug(
                "load_labeled: store reload failed for index=%s: %s — falling through",
                page_index,
                exc,
            )
            return None

    def load_cached(self, page_index: int) -> PageLoadOutcome | None:
        """STUB: cached lane retired (M5b). Returns None — labeled lane handles reload."""
        return None

    def run_ocr(self, page_index: int, *, edited_image_bytes: bytes | None = None) -> PageLoadOutcome:
        if page_index < 0 or page_index >= len(self.project.image_paths):
            raise IndexError(
                f"page_index {page_index} out of range (total_pages={len(self.project.image_paths)})"
            )
        source_path = self.project.image_paths[page_index]

        # Lane A / Task A4: when the caller supplies the post-erase edited image
        # bytes (legacy "Reload OCR (Edited)"), OCR against those instead of the
        # pristine on-disk source. The bytes are materialised to a temp file
        # alongside the source so the source_identifier / filename is preserved.
        _tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        if edited_image_bytes is not None:
            _tmp_dir = tempfile.TemporaryDirectory()
            image_path = Path(_tmp_dir.name) / source_path.name
            image_path.write_bytes(edited_image_bytes)
        else:
            image_path = source_path
            if not image_path.exists():
                raise PageImageNotFoundError(f"Page image not found on disk: {image_path}")

        try:
            return self._run_ocr_on_path(page_index, image_path)
        finally:
            if _tmp_dir is not None:
                _tmp_dir.cleanup()

    def _run_ocr_on_path(self, page_index: int, image_path: Path) -> PageLoadOutcome:
        """Run OCR against a concrete on-disk image path (Lane A / A4 seam).

        Split out of ``run_ocr`` so the edited-image temp-file path and the
        pristine source path share one code path; ``run_ocr`` owns the temp
        directory lifecycle.
        """
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

        # Attach the cv2 image + reorganize the page (Lane A / Task A1,
        # legacy parity: operations/ocr/page_operations.py:305-355). Without
        # the image attached, ``word.refine_bbox(page.cv2_numpy_page_image)``
        # has nothing to refine against. ``reorganize_page`` re-derives the
        # paragraph/line/word hierarchy from the freshly OCR'd boxes.
        try:
            import cv2

            cv2_image = cv2.imread(str(image_path))
            if cv2_image is not None:
                object.__setattr__(page_obj, "cv2_numpy_page_image", cv2_image)
            reorganize = getattr(page_obj, "reorganize_page", None)
            if callable(reorganize):
                reorganize()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "cv2 image attach / reorganize failed for index=%s name=%s: %s",
                page_index,
                image_path.name,
                exc,
            )

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

        # Event-store write: persist OCR result as OcrCompleted event.
        # Best-effort: a write failure must not turn a successful OCR
        # result into a 5xx — the in-memory outcome is still returned.
        # After a successful write, the returned PageLoadOutcome carries
        # the ``page_id`` from the aggregate so callers can stamp it on
        # ``PageState.page_id`` for subsequent event-store mutations.
        if self.store is not None:
            try:
                image_bytes = image_path.read_bytes()
                agg = _ingest_ocr_result(
                    page=page_obj,
                    image_bytes=image_bytes,
                    page_index=page_index,
                    store=self.store,
                    project=self.project,
                )
                # Stamp the page_id from the aggregate onto the page object
                # so callers can transfer it to PageState.page_id.
                # Use setattr to avoid basedpyright reportAttributeAccessIssue on
                # the typed Page class — this is a dynamic sidecar attr, not a
                # part of the Page API.
                object.__setattr__(page_obj, "_labeler_page_id", agg.record.page_id)
                logger.debug(
                    "run_ocr: wrote OCR result to event store page_id=%s page=%d",
                    agg.record.page_id,
                    page_index,
                )
            except Exception as exc:
                logger.warning(
                    "run_ocr: event-store write failed for page=%d: %s — returning in-memory result",
                    page_index,
                    exc,
                )

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
