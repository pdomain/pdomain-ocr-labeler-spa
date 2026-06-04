"""Tests for core/jobs/handlers/export.py — issue #226.

Acceptance:
- All-validated scope iterates only fully-validated saved pages
- Style subfolder per selected style label; "all" when no filter
- Cancel mid-export: partial output deleted; cancelled SSE event emitted
- WordFilter matches/excludes correctly
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdomain_ocr_labeler_spa.core.jobs.handlers.export import (
    WordFilter,
    _labeled_project_dir,
    _page_is_validated,
    _scan_labeled_pages,
    export_output_dir,
)

# ---------------------------------------------------------------------------
# WordFilter
# ---------------------------------------------------------------------------


def _make_word(style_labels=None, word_components=None):
    w = MagicMock()
    w.text_style_labels = style_labels or []
    w.word_components = word_components or []
    return w


def test_word_filter_empty_matches_all() -> None:
    wf = WordFilter()
    assert wf.matches(_make_word())
    assert wf.matches(_make_word(style_labels=["italics"]))


def test_word_filter_style_includes_matching() -> None:
    wf = WordFilter(style_labels=frozenset(["italics"]))
    assert wf.matches(_make_word(style_labels=["italics"]))


def test_word_filter_style_excludes_non_matching() -> None:
    wf = WordFilter(style_labels=frozenset(["italics"]))
    assert not wf.matches(_make_word(style_labels=["small caps"]))


def test_word_filter_component_matches() -> None:
    wf = WordFilter(word_components=frozenset(["footnote marker"]))
    assert wf.matches(_make_word(word_components=["footnote marker"]))
    assert not wf.matches(_make_word(word_components=["drop cap"]))


def test_word_filter_combined_both_required() -> None:
    wf = WordFilter(style_labels=frozenset(["italics"]), word_components=frozenset(["superscript"]))
    # Both must match.
    assert wf.matches(_make_word(style_labels=["italics"], word_components=["superscript"]))
    # Only one matching — fails.
    assert not wf.matches(_make_word(style_labels=["italics"], word_components=[]))


# ---------------------------------------------------------------------------
# Page validation
# ---------------------------------------------------------------------------


def _make_page(word_labels_list):
    """Build a mock Page with words carrying the given word_labels."""
    words = []
    for labels in word_labels_list:
        w = MagicMock()
        w.word_labels = labels
        words.append(w)
    page = MagicMock()
    page.words = words
    return page


def test_page_is_validated_all_validated() -> None:
    page = _make_page([["validated"], ["validated"]])
    assert _page_is_validated(page)


def test_page_is_validated_some_not_validated() -> None:
    page = _make_page([["validated"], []])
    assert not _page_is_validated(page)


def test_page_is_validated_empty_page() -> None:
    page = _make_page([])
    assert not _page_is_validated(page)


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def test_labeled_project_dir(tmp_path: Path) -> None:
    p = _labeled_project_dir(tmp_path, "myproj")
    assert p == tmp_path / "labeled-projects" / "myproj"


def test_export_output_dir(tmp_path: Path) -> None:
    p = export_output_dir(tmp_path, "myproj", "italics")
    assert p == tmp_path / "doctr-export" / "myproj" / "italics"


def test_export_output_dir_all(tmp_path: Path) -> None:
    p = export_output_dir(tmp_path, "myproj", "all")
    assert p == tmp_path / "doctr-export" / "myproj" / "all"


def test_scan_labeled_pages_empty_when_missing(tmp_path: Path) -> None:
    result = _scan_labeled_pages(tmp_path, "nonexistent")
    assert result == []


def test_scan_labeled_pages_returns_jsons(tmp_path: Path) -> None:
    proj_dir = tmp_path / "labeled-projects" / "myproj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "myproj_000.json").write_text("{}")
    (proj_dir / "myproj_001.json").write_text("{}")
    result = _scan_labeled_pages(tmp_path, "myproj")
    assert len(result) == 2
    assert all(p.suffix == ".json" for p in result)


# ---------------------------------------------------------------------------
# handle_export — integration (mocked pdomain-book-tools)
# ---------------------------------------------------------------------------


def _write_envelope(path: Path, validated: bool = True) -> None:
    """Write a minimal envelope JSON (with or without validated word_labels)."""
    word_labels = ["validated"] if validated else []
    data = {
        "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
        "payload": {
            "page": {
                "index": 0,
                "words": [
                    {
                        "text": "hello",
                        "word_labels": word_labels,
                        "bounding_box": {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
                    }
                ],
            }
        },
    }
    path.write_text(json.dumps(data))


def _make_runner_with_settings(tmp_path: Path):
    """Create a JobRunner with settings pointing at tmp_path."""
    from pdomain_ocr_labeler_spa.core.jobs import JobEventBroker, JobRunner
    from pdomain_ocr_labeler_spa.settings import Settings

    settings = Settings(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        config_root=tmp_path / "config",
    )
    broker = JobEventBroker()
    runner = JobRunner(broker, context={"settings": settings})
    return runner, settings


@pytest.mark.asyncio
async def test_handle_export_no_pages_completes(tmp_path: Path) -> None:
    """Handler completes successfully even with zero pages."""
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import handle_export
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job

    runner, _settings = _make_runner_with_settings(tmp_path)
    job = Job(
        job_id="j1",
        job_type="export",
        project_id="myproj",
        payload={"scope": "all_validated"},
        created_at=datetime.now(UTC),
    )
    runner._jobs["j1"] = job
    # No labeled files exist — should complete without error.
    await handle_export(runner, job)


@pytest.mark.asyncio
async def test_handle_export_style_subfolder(tmp_path: Path) -> None:
    """Style filter produces correct subfolder name."""
    data_root = tmp_path / "data"
    proj_dir = data_root / "labeled-projects" / "proj1"
    proj_dir.mkdir(parents=True)
    # Create a dummy json + png.
    _write_envelope(proj_dir / "proj1_000.json", validated=True)
    (proj_dir / "proj1_000.png").write_bytes(b"\x00")

    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import handle_export
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job

    runner, settings = _make_runner_with_settings(tmp_path)
    settings.__dict__["data_root"] = data_root  # override in test  # pyright: ignore[reportIndexIssue]

    # Patch _export_page to avoid cv2 dependency in unit tests.
    with (
        patch("pdomain_ocr_labeler_spa.core.jobs.handlers.export._export_page") as mock_ep,
        patch("pdomain_ocr_labeler_spa.core.jobs.handlers.export._load_page_from_envelope_file") as mock_load,
    ):
        mock_page = _make_page([["validated"]])
        mock_load.return_value = mock_page

        job = Job(
            job_id="j2",
            job_type="export",
            project_id="proj1",
            payload={"scope": "all_validated", "style_filters": ["italics"]},
            created_at=datetime.now(UTC),
        )
        runner._jobs["j2"] = job
        runner.context["settings"] = MagicMock(data_root=data_root)

        await handle_export(runner, job)

    # Verify _export_page called with italics subfolder.
    assert mock_ep.called
    call_args = mock_ep.call_args
    output_dir_arg = call_args[0][2]  # positional arg 3
    assert "italics" in str(output_dir_arg)


@pytest.mark.asyncio
async def test_handle_export_cancel_removes_partial_output(tmp_path: Path) -> None:
    """Cancel during export deletes partial output directory."""
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import handle_export
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job

    data_root = tmp_path / "data"
    proj_dir = data_root / "labeled-projects" / "proj2"
    proj_dir.mkdir(parents=True)
    # Create 3 pages.
    for i in range(3):
        _write_envelope(proj_dir / f"proj2_{i:03d}.json", validated=True)
        (proj_dir / f"proj2_{i:03d}.png").write_bytes(b"\x00")

    # Create partial output to verify it's cleaned up.
    partial_dir = data_root / "doctr-export" / "proj2"
    partial_dir.mkdir(parents=True)
    (partial_dir / "partial.txt").write_text("partial")

    runner, _settings = _make_runner_with_settings(tmp_path)
    runner.context["settings"] = MagicMock(data_root=data_root)

    call_count = 0

    with (
        patch("pdomain_ocr_labeler_spa.core.jobs.handlers.export._export_page"),
        patch("pdomain_ocr_labeler_spa.core.jobs.handlers.export._load_page_from_envelope_file") as mock_load,
    ):

        def side_effect(path):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                # Simulate cancel on second page by updating job status.
                from pdomain_ocr_labeler_spa.core.jobs.runner import JobStatus

                job_in_runner = runner._jobs.get("j3")
                if job_in_runner:
                    runner._jobs["j3"] = job_in_runner.model_copy(update={"status": JobStatus.CANCELLED})
            return _make_page([["validated"]])

        mock_load.side_effect = side_effect

        job = Job(
            job_id="j3",
            job_type="export",
            project_id="proj2",
            payload={"scope": "all_validated"},
            created_at=datetime.now(UTC),
        )
        runner._jobs["j3"] = job
        await handle_export(runner, job)

    # Partial output directory must have been removed.
    assert not partial_dir.exists()


# ---------------------------------------------------------------------------
# Lane E2 — per-style separate-subfolder export
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_export_two_styles_two_subfolders(tmp_path: Path) -> None:
    """Two selected styles produce two separate subfolders in one run.

    Lane E2 (plan docs/plans/2026-06-03-labeler-spa-legacy-parity.md): legacy
    runs one export per selected style into separate subfolders. Each
    subfolder must receive a WordFilter scoped to exactly that style.
    """
    data_root = tmp_path / "data"
    proj_dir = data_root / "labeled-projects" / "proj_e2"
    proj_dir.mkdir(parents=True)
    _write_envelope(proj_dir / "proj_e2_000.json", validated=True)
    (proj_dir / "proj_e2_000.png").write_bytes(b"\x00")

    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import handle_export
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job

    runner, _settings = _make_runner_with_settings(tmp_path)
    runner.context["settings"] = MagicMock(data_root=data_root)

    with (
        patch("pdomain_ocr_labeler_spa.core.jobs.handlers.export._export_page") as mock_ep,
        patch("pdomain_ocr_labeler_spa.core.jobs.handlers.export._load_page_from_envelope_file") as mock_load,
    ):
        mock_load.return_value = _make_page([["validated"]])

        job = Job(
            job_id="je2",
            job_type="export",
            project_id="proj_e2",
            payload={"scope": "all_validated", "style_filters": ["italics", "small caps"]},
            created_at=datetime.now(UTC),
        )
        runner._jobs["je2"] = job
        await handle_export(runner, job)

    # Two _export_page calls (one page x two style subfolders).
    assert mock_ep.call_count == 2

    # Collect (subfolder_path, word_filter_styles) for each call.
    seen: dict[str, frozenset[str]] = {}
    for call in mock_ep.call_args_list:
        output_dir = call.args[2]
        wf = call.kwargs["word_filter"]
        seen[output_dir.name] = wf.style_labels if wf is not None else frozenset()

    assert set(seen) == {"italics", "small caps"}
    # Each subfolder is scoped to exactly its own style — not a combined filter.
    assert seen["italics"] == frozenset({"italics"})
    assert seen["small caps"] == frozenset({"small caps"})


# ---------------------------------------------------------------------------
# Lane E3 stats — double-count bug regression (two-style export)
# ---------------------------------------------------------------------------


def _make_stats_word(validated: bool = True, text: str = "hello") -> MagicMock:
    """Build a mock word with bbox + text that passes _word_has_bbox/_word_has_text."""
    w = MagicMock()
    w.word_labels = ["validated"] if validated else []
    w.text = text
    w.ground_truth_text = text
    w.text_style_labels = []
    w.word_components = []
    w.bounding_box = object()  # non-None → _word_has_bbox returns True
    w.ground_truth_bounding_box = None
    return w


def _make_page_with_stats_words(word_mocks: list) -> MagicMock:
    """Build a mock page whose .words list carries stats-capable word mocks."""
    page = MagicMock()
    page.words = word_mocks
    return page


@pytest.mark.asyncio
async def test_export_stats_not_doubled_for_two_style_export(tmp_path: Path) -> None:
    """E3 stats: a two-style export counts each page ONCE, not once per subfolder.

    Regression guard for the double-count bug: when ``style_filters`` has two
    entries the per-subfolder loop ran ``_count_exported_words`` per subfolder,
    inflating the terminal stats by the subfolder count.  After the fix, a
    single page with two validated+bbox+text words must yield
    ``words_exported_detection == 2`` and ``words_exported_recognition == 2``
    even when two style subfolders are selected.
    """
    from datetime import UTC, datetime

    from pdomain_ocr_labeler_spa.core.jobs.handlers.export import handle_export
    from pdomain_ocr_labeler_spa.core.jobs.runner import Job

    data_root = tmp_path / "data"
    proj_dir = data_root / "labeled-projects" / "proj_e3_stats"
    proj_dir.mkdir(parents=True)
    _write_envelope(proj_dir / "proj_e3_stats_000.json", validated=True)
    (proj_dir / "proj_e3_stats_000.png").write_bytes(b"\x00")

    # One page with 2 words that both have bbox and text.
    page = _make_page_with_stats_words(
        [
            _make_stats_word(validated=True, text="alpha"),
            _make_stats_word(validated=True, text="beta"),
        ]
    )

    runner, _settings = _make_runner_with_settings(tmp_path)
    runner.context["settings"] = MagicMock(data_root=data_root)

    with (
        patch("pdomain_ocr_labeler_spa.core.jobs.handlers.export._export_page"),
        patch("pdomain_ocr_labeler_spa.core.jobs.handlers.export._load_page_from_envelope_file") as mock_load,
    ):
        mock_load.return_value = page

        job = Job(
            job_id="je3_stats",
            job_type="export",
            project_id="proj_e3_stats",
            # Two style subfolders — previously doubled the stats.
            payload={"scope": "all_validated", "style_filters": ["italics", "small caps"]},
            created_at=datetime.now(UTC),
        )
        runner._jobs["je3_stats"] = job
        await handle_export(runner, job)

    # Retrieve the last update_progress result (terminal call carries result dict).
    final_job = runner._jobs["je3_stats"]
    result = final_job.result

    # Exactly 2 detection words and 2 recognition words — NOT 4 (2 x 2 subfolders).
    assert result.get("words_exported_detection") == 2, (
        f"Expected 2, got {result.get('words_exported_detection')} — "
        "likely the double-count bug (counted once per style subfolder)"
    )
    assert result.get("words_exported_recognition") == 2, (
        f"Expected 2, got {result.get('words_exported_recognition')} — "
        "likely the double-count bug (counted once per style subfolder)"
    )
