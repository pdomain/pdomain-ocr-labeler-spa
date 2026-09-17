"""Tests for the source-image drift signal — issue
2026-07-21-image-drift-banner-hard-off.

``_image_drift_for_page`` compares a page's recorded OCR-time image digest
(``_image_digest_for_page`` — ``ProvenanceNode.blob_refs[1]``) against the
file its project currently names on disk. The first check for a page (no
cached baseline yet — a fresh process, or a fresh OCR generation) hashes the
file once and compares it directly to the recorded digest, so a page whose
image was replaced before this process ever looked at it is still caught
immediately. Every later check of the same page takes the cheap path:
compare ``st_size`` / ``st_mtime_ns`` cached on ``PageState`` against the
current stat, and only re-hash when those moved.

These tests call ``_image_drift_for_page`` directly against a real
``LabelerPageStore`` (same event-store-write pattern
``test_local_doctr_page_store.py`` uses) rather than spinning up doctr OCR —
what matters here is the digest-vs-disk comparison, not OCR itself.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

import pdomain_ocr_labeler_spa.api.pages as pages_mod
from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.api.pages import ImageDrift, _image_drift_for_page
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import PageState, ProjectState


def _make_page_stub(page_id: UUID | None = None) -> MagicMock:
    """Minimal duck-typed ``Page`` — mirrors ``test_local_doctr_page_store.py``."""
    page = MagicMock()
    page.page_id = page_id or uuid4()
    page.to_dict.return_value = {"page_id": str(page.page_id), "lines": []}
    return page


def _load_ocrd_page(
    tmp_path: Path, image_bytes: bytes
) -> tuple[ProjectState, PageState, Path, LabelerPageStore]:
    """Set up a one-page project whose recorded digest matches ``image_bytes``."""
    image_path = tmp_path / "001.png"
    image_path.write_bytes(image_bytes)

    store = LabelerPageStore(project_dir=tmp_path)
    fake_page = _make_page_stub()
    agg = _ingest_ocr_result(page=fake_page, image_bytes=image_bytes, page_index=0, store=store)

    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=[image_path],
        total_pages=1,
        ground_truth_map={},
    )
    project_state = ProjectState()
    project_state.set_loaded_project(project)

    pstate = PageState(page_index=0, page_id=agg.record.page_id)
    project_state.set_page_state(0, pstate)
    return project_state, pstate, image_path, store


def _load_page_ocrd_on_edited_bytes(
    tmp_path: Path, *, disk_bytes: bytes, edited_bytes: bytes
) -> tuple[ProjectState, PageState, Path, LabelerPageStore]:
    """Simulate "erase pixels" + "Reload OCR (Edited)": OCR ran against
    ``edited_bytes`` (so the recorded digest is the edited image's hash, per
    ``local_doctr.py``'s ``run_ocr(edited_image_bytes=...)`` /
    ``_run_ocr_on_path`` /  ``_ingest_ocr_result``), while the on-disk source
    file still holds the untouched ``disk_bytes``. ``pstate.edited_image_blob``
    is stamped with the same content hash ``_persist_edited_image_blob`` would
    record — both are sha256 of the identical edited bytes via the
    content-addressed blob store, so they match exactly the way the real
    erase + reload-ocr-edited flow produces.
    """
    image_path = tmp_path / "001.png"
    image_path.write_bytes(disk_bytes)

    store = LabelerPageStore(project_dir=tmp_path)
    fake_page = _make_page_stub()
    agg = _ingest_ocr_result(page=fake_page, image_bytes=edited_bytes, page_index=0, store=store)

    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=[image_path],
        total_pages=1,
        ground_truth_map={},
    )
    project_state = ProjectState()
    project_state.set_loaded_project(project)

    pstate = PageState(page_index=0, page_id=agg.record.page_id)
    pstate.edited_image_blob = hashlib.sha256(edited_bytes).hexdigest()
    project_state.set_page_state(0, pstate)
    return project_state, pstate, image_path, store


def test_first_check_records_baseline_and_reports_no_drift(tmp_path: Path) -> None:
    """No prior baseline on ``pstate`` and the file matches its recorded
    digest — the first check hashes once, confirms no drift, and caches the
    baseline so later checks can take the cheap path.
    """
    project_state, pstate, _image_path, store = _load_ocrd_page(tmp_path, b"\x89PNG\r\n original bytes")

    result = _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    assert result is None
    assert pstate.image_drift_digest is not None
    assert pstate.image_drift_size is not None
    assert pstate.image_drift_mtime_ns is not None


def test_changed_image_reports_drift_on_first_check(tmp_path: Path) -> None:
    """A file replaced while no baseline is cached yet — e.g. the server was
    down when the replacement happened, so this process never saw the
    original bytes — must report drift on the very first check, not just
    the second one.
    """
    project_state, pstate, image_path, store = _load_ocrd_page(tmp_path, b"\x89PNG\r\n original bytes")
    image_path.write_bytes(b"\x89PNG\r\n replaced bytes, different content")

    result = _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    assert isinstance(result, ImageDrift)
    assert result.error == "image_changed"


def test_unchanged_image_reports_no_drift_on_second_check(tmp_path: Path) -> None:
    """The first check hashes once and caches the baseline; a second check of
    the same unchanged file must take the cheap stat path and not hash again.
    """
    project_state, pstate, _image_path, store = _load_ocrd_page(tmp_path, b"\x89PNG\r\n original bytes")
    # First check: no baseline yet, so this legitimately hashes once to
    # establish it (see test_first_check_records_baseline_and_reports_no_drift).
    _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    def _boom(_data: bytes) -> object:
        raise AssertionError("cheap path must not hash again when stat is unchanged")

    original_sha256 = pages_mod.hashlib.sha256
    pages_mod.hashlib.sha256 = _boom  # type: ignore[assignment]
    try:
        result = _image_drift_for_page(
            project_state=project_state, page_index=0, pstate=pstate, page_store=store
        )
    finally:
        pages_mod.hashlib.sha256 = original_sha256

    assert result is None


def test_changed_image_reports_drift(tmp_path: Path) -> None:
    """The source image's bytes changed on disk after OCR — reports drift."""
    project_state, pstate, image_path, store = _load_ocrd_page(tmp_path, b"\x89PNG\r\n original bytes")
    _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    # Rewrite with different content and force the mtime forward so the
    # cheap stat check actually trips (some filesystems have coarse mtime
    # resolution; os.utime pins it unambiguously).
    image_path.write_bytes(b"\x89PNG\r\n replaced bytes, different content")
    new_mtime_ns = (pstate.image_drift_mtime_ns or 0) + 10_000_000_000
    os.utime(image_path, ns=(new_mtime_ns, new_mtime_ns))

    result = _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    assert isinstance(result, ImageDrift)
    assert result.error == "image_changed"
    assert "001.png" in result.message


def test_touched_without_content_change_reports_no_drift_and_refreshes_baseline(tmp_path: Path) -> None:
    """Stat moves but the bytes come back identical — no drift, baseline refreshed."""
    project_state, pstate, image_path, store = _load_ocrd_page(tmp_path, b"\x89PNG\r\n original bytes")
    _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    original_size = pstate.image_drift_size
    original_mtime_ns = pstate.image_drift_mtime_ns
    # Rewrite identical bytes with a distinct mtime (touch-without-edit).
    image_path.write_bytes(b"\x89PNG\r\n original bytes")
    new_mtime_ns = (original_mtime_ns or 0) + 10_000_000_000
    os.utime(image_path, ns=(new_mtime_ns, new_mtime_ns))

    result = _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    assert result is None
    assert pstate.image_drift_size == original_size
    assert pstate.image_drift_mtime_ns == new_mtime_ns


def test_missing_digest_reports_no_drift(tmp_path: Path) -> None:
    """A page with no recorded OCR-time digest yet can't be compared."""
    image_path = tmp_path / "001.png"
    image_path.write_bytes(b"\x89PNG\r\n bytes")
    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=[image_path],
        total_pages=1,
        ground_truth_map={},
    )
    project_state = ProjectState()
    project_state.set_loaded_project(project)
    pstate = PageState(page_index=0, page_id=None)
    project_state.set_page_state(0, pstate)

    result = _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=None)

    assert result is None


def test_unreadable_file_reports_no_drift(tmp_path: Path) -> None:
    """The recorded digest exists but the on-disk file is gone — no false alarm."""
    project_state, pstate, image_path, store = _load_ocrd_page(tmp_path, b"\x89PNG\r\n original bytes")
    image_path.unlink()

    result = _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    assert result is None


def test_reload_ocr_edited_reports_no_drift_on_either_fetch(tmp_path: Path) -> None:
    """ "Reload OCR (Edited)" OCRs the persisted post-erase image, not the
    pristine on-disk source, so the recorded digest is the edited bytes'
    hash and will never match the untouched disk file. That mismatch is not
    drift — the page must not permanently show the drift banner, whose
    advice (plain Reload OCR) would discard the user's edited OCR result.
    """
    project_state, pstate, _image_path, store = _load_page_ocrd_on_edited_bytes(
        tmp_path,
        disk_bytes=b"\x89PNG\r\n pristine disk bytes",
        edited_bytes=b"\x89PNG\r\n erased/edited bytes",
    )

    first = _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)
    second = _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    assert first is None
    assert second is None


def test_reload_ocr_edited_still_detects_a_later_genuine_disk_change(tmp_path: Path) -> None:
    """Drift detection stays alive after an edited-OCR generation: once the
    baseline is re-anchored to the pristine disk file, a real subsequent
    on-disk change must still be caught.
    """
    project_state, pstate, image_path, store = _load_page_ocrd_on_edited_bytes(
        tmp_path,
        disk_bytes=b"\x89PNG\r\n pristine disk bytes",
        edited_bytes=b"\x89PNG\r\n erased/edited bytes",
    )
    # Establishes the re-anchored baseline against the pristine disk bytes.
    _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    image_path.write_bytes(b"\x89PNG\r\n a genuinely different replacement image")
    new_mtime_ns = (pstate.image_drift_mtime_ns or 0) + 10_000_000_000
    os.utime(image_path, ns=(new_mtime_ns, new_mtime_ns))

    result = _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    assert isinstance(result, ImageDrift)
    assert result.error == "image_changed"


def test_book_labeling_session_skips_the_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Book-labeling projects skip the check entirely (see docstring on
    ``_image_drift_for_page`` — the verified manifest lease already covers
    a changed source, and a fresh sealed memfd's stat changes every request).
    """
    project_state, pstate, image_path, store = _load_ocrd_page(tmp_path, b"\x89PNG\r\n original bytes")
    _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)
    image_path.write_bytes(b"\x89PNG\r\n replaced bytes, definitely different")

    monkeypatch.setattr(ProjectState, "has_book_labeling_session", property(lambda _self: True))

    result = _image_drift_for_page(project_state=project_state, page_index=0, pstate=pstate, page_store=store)

    assert result is None
