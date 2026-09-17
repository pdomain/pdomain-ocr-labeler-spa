"""Unit tests for the shared ``leased_labeling_page`` job-handler helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdomain_ocr_labeler_spa.api.projects import _build_project_from_book_labeling_manifest
from pdomain_ocr_labeler_spa.core.jobs.handlers._labeling_page_lease import leased_labeling_page
from pdomain_ocr_labeler_spa.core.persistence.book_labeling_manifest import (
    load_book_labeling_manifest_directory,
)
from pdomain_ocr_labeler_spa.core.persistence.book_labeling_session import BookLabelingSession
from pdomain_ocr_labeler_spa.core.project_state import ProjectState
from tests.unit.core.persistence.test_book_labeling_session import _write_book


def _book_project_state(root: Path, *, page_count: int = 2) -> ProjectState:
    """A ``ProjectState`` loaded against a verified book-labeling manifest."""
    _write_book(root, page_count=page_count, valid_images=True)
    session = BookLabelingSession(load_book_labeling_manifest_directory(root))
    project = _build_project_from_book_labeling_manifest(session)
    project_state = ProjectState()
    project_state.set_loaded_project(project, book_labeling_session=session)
    return project_state


def test_an_ordinary_project_has_nothing_to_lease(tmp_path: Path) -> None:
    """No labeling bundle, no book session: ``labeling_image_path`` stays the raw path."""
    from pdomain_ocr_labeler_spa.core.models import Project

    image_path = tmp_path / "000.png"
    image_path.write_bytes(b"\x89PNG\r\n")
    project = Project(
        project_id="plain",
        project_root=tmp_path,
        image_paths=[image_path],
        ground_truth_map={},
        total_pages=1,
    )
    project_state = ProjectState()
    project_state.set_loaded_project(project)

    with leased_labeling_page(project_state, 0):
        assert project_state.labeling_image_path(0) == image_path


def test_a_book_project_resolves_a_sealed_descriptor_while_bound(tmp_path: Path) -> None:
    project_state = _book_project_state(tmp_path / "book")

    with leased_labeling_page(project_state, 0):
        resolved = project_state.labeling_image_path(0)
        assert str(resolved).startswith("/proc/self/fd/")
        assert resolved.read_bytes()  # the descriptor is live and readable


def test_the_lease_is_closed_after_a_successful_block(tmp_path: Path) -> None:
    project_state = _book_project_state(tmp_path / "book")

    with leased_labeling_page(project_state, 0):
        resolved = project_state.labeling_image_path(0)

    with pytest.raises(OSError):
        resolved.read_bytes()


def test_the_lease_is_closed_when_the_block_raises(tmp_path: Path) -> None:
    project_state = _book_project_state(tmp_path / "book")
    resolved_paths: list[Path] = []

    def _open_and_raise() -> None:
        with leased_labeling_page(project_state, 0):
            resolved_paths.append(project_state.labeling_image_path(0))
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _open_and_raise()

    assert len(resolved_paths) == 1
    with pytest.raises(OSError):
        resolved_paths[0].read_bytes()


def test_a_tampered_manifest_page_raises_value_error_with_no_lease_to_close(tmp_path: Path) -> None:
    """``open_labeling_page`` converts the book session's verification failure
    into ``ValueError`` before any descriptor is handed back — callers looping
    over many pages catch this per page and move on."""
    root = tmp_path / "book"
    project_state = _book_project_state(root, page_count=2)
    project = project_state.loaded_project
    assert project is not None
    tampered = (
        root
        / "pages"
        / next(p.name for p in (root / "pages").iterdir() if p.name.startswith("0000-"))
        / "materialization.json"
    )
    tampered.write_bytes(b"{}\n")

    with (
        pytest.raises(ValueError, match="unable to resolve verified book page 0"),
        leased_labeling_page(project_state, 0),
    ):
        pass  # pragma: no cover - never reached
