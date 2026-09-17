"""Unit tests for the shared measure-and-fit pass over one book."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pdomain_pgdp_measure.profile_input import ProfileInputPage
from pdomain_pgdp_measure.profile_models import PageMeasurement, ProfileDiagnostic

from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.project_state import ProjectState


def _fake_measurement(project_id: str, page: ProfileInputPage) -> PageMeasurement:
    del project_id
    # ``PageMeasurement.__post_init__`` requires an unavailable measurement
    # (every foreground field ``None``) to carry an ``image_missing`` or
    # ``image_unreadable`` diagnostic — the same shape ``profile_page`` itself
    # returns for a page it could not decode. A bare ``Mock`` would hide that
    # constraint instead of catching a real shape mismatch, which is why the
    # test builds a real ``PageMeasurement`` here rather than one.
    return PageMeasurement(
        page_name=page.name,
        source_path=page.source_path or f"book1/{page.name}",
        sha256=None,
        source_frame=None,
        image_mode=None,
        grayscale_threshold=None,
        foreground_pixels=None,
        foreground_bounds=None,
        margins=None,
        ink_bands=None,
        diagnostics=(ProfileDiagnostic(code="image_missing", message="test fixture"),),
    )


def _project_state(tmp_path: Path, *, page_count: int) -> tuple[ProjectState, Project]:
    """An ordinary (non-book-labeling) project.

    A real ``ProjectState`` with no book-labeling session, rather than a hand
    written stand-in: ``open_labeling_page`` returns ``None`` and
    ``labeling_image_path`` degrades to ``image_paths[i]`` unchanged on this
    path, which is exactly what a stand-in would need to reproduce — the real
    class does it for free and keeps the test honest about the production
    type ``measure_book`` is typed to take.
    """
    image_paths = [tmp_path / f"00{n}.png" for n in range(1, page_count + 1)]
    project = Project(
        project_id="book1",
        project_root=tmp_path,
        image_paths=image_paths,
        ground_truth_map={},
        total_pages=page_count,
    )
    project_state = ProjectState()
    project_state.set_loaded_project(project)
    return project_state, project


def test_measure_book_measures_every_image_path_and_reports_progress(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_measurement import measure_book

    seen: list[tuple[int, int]] = []

    async def on_page_measured(current: int, total: int) -> None:
        seen.append((current, total))

    project_state, project = _project_state(tmp_path, page_count=3)
    result = asyncio.run(
        measure_book(
            project,
            project_state=project_state,
            measure_fn=_fake_measurement,
            on_page_measured=on_page_measured,
        )
    )

    assert len(result.measurements) == 3
    assert [m.page_name for m in result.measurements] == ["001.png", "002.png", "003.png"]
    assert result.page_indices == (0, 1, 2)
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_measure_book_returns_one_classification_per_measured_page(tmp_path: Path) -> None:
    """classify_pages preserves input order, so page_index is recovered by position.

    That order-preservation is documented behaviour, not a type-checked contract,
    so the length check is what makes relying on it safe.
    """
    from pdomain_ocr_labeler_spa.core.page_measurement import measure_book

    async def _noop(current: int, total: int) -> None:
        del current, total

    project_state, project = _project_state(tmp_path, page_count=3)
    result = asyncio.run(
        measure_book(
            project,
            project_state=project_state,
            measure_fn=_fake_measurement,
            on_page_measured=_noop,
        )
    )
    assert len(result.classifications) == len(result.measurements)


def test_measure_book_on_a_book_with_no_pages_returns_empty(tmp_path: Path) -> None:
    from pdomain_ocr_labeler_spa.core.page_measurement import measure_book

    async def _noop(current: int, total: int) -> None:
        del current, total

    project_state, project = _project_state(tmp_path, page_count=0)
    result = asyncio.run(
        measure_book(
            project,
            project_state=project_state,
            measure_fn=_fake_measurement,
            on_page_measured=_noop,
        )
    )
    assert result.measurements == ()
    assert result.classifications == ()
    assert result.page_indices == ()
    assert result.templates.has_type_page is False
