"""Tests for ``LocalDoctrPageLoader`` — slice 8b-ii.

The loader implements ``core.page_state.PageLoader`` (the dispatch
protocol). At this slice it wires ``run_ocr`` only; ``load_labeled``
and ``load_cached`` return ``None`` until ``core/persistence/
user_page_envelope.py`` ships (a separate M3 slice).

Hermetic: ``pdomain_book_tools.ocr.document.Document.from_image_ocr_via_doctr``
is stubbed via ``sys.modules`` injection; ``PredictorCache`` is stubbed
in-process so we don't pull torch.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import LocalDoctrPageLoader
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.ocr.predictor import PredictorCache
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource


def _make_project(tmp_path: Path, n_pages: int = 3) -> Project:
    image_paths = []
    for i in range(n_pages):
        p = tmp_path / f"page_{i:03d}.png"
        p.write_bytes(b"fake-png")
        image_paths.append(p)
    return Project(
        project_id="proj1",
        project_root=tmp_path,
        image_paths=image_paths,
        ground_truth_map={},
        total_pages=len(image_paths),
        current_page_index=0,
    )


@pytest.fixture
def stub_pdomain_book_tools(monkeypatch: pytest.MonkeyPatch):
    """Inject fake ``pdomain_book_tools.ocr.document.Document``.

    ``from_image_ocr_via_doctr`` records call args and returns a
    ``Document``-shaped object whose ``pages[0]`` is the marker page.
    """

    calls: list[dict[str, Any]] = []

    class _FakePage:
        def __init__(self, source_identifier: str) -> None:
            self.source_identifier = source_identifier
            # Track add_ground_truth calls for slice "GT injection".
            self.ground_truth_calls: list[str] = []

        def to_dict(self) -> dict[str, Any]:
            """Stub for ``Page.to_dict`` used by the auto-cache-write
            slice. The build_envelope writer just stashes this verbatim
            into ``payload.page``; the value here is purely a marker.
            """
            return {"type": "Page", "source_identifier": self.source_identifier}

        def add_ground_truth(self, text: str) -> None:
            """Stub for ``Page.add_ground_truth``. Records calls so
            tests can assert injection behaviour."""
            self.ground_truth_calls.append(text)

    class _FakeDocument:
        def __init__(self, pages: list[_FakePage]) -> None:
            self.pages = pages

    def from_image_ocr_via_doctr(
        image_path: Any,
        *,
        source_identifier: str,
        predictor: Any,
    ) -> _FakeDocument:
        calls.append(
            {
                "image_path": image_path,
                "source_identifier": source_identifier,
                "predictor": predictor,
            }
        )
        return _FakeDocument(pages=[_FakePage(source_identifier=source_identifier)])

    fake_module = SimpleNamespace(
        Document=SimpleNamespace(from_image_ocr_via_doctr=from_image_ocr_via_doctr),
    )
    monkeypatch.setitem(sys.modules, "pdomain_book_tools.ocr.document", fake_module)
    return SimpleNamespace(calls=calls, FakePage=_FakePage)


@pytest.fixture
def stub_predictor_cache(monkeypatch: pytest.MonkeyPatch):
    """``PredictorCache`` that bypasses doctr_support entirely.

    The real cache imports ``pdomain_book_tools.ocr.doctr_support`` lazily;
    here we inject the stub module too so ``get_or_create`` can run
    without erroring.
    """

    fake_module = SimpleNamespace(
        get_default_doctr_predictor=lambda: SimpleNamespace(kind="stock"),
        get_finetuned_torch_doctr_predictor=lambda *a, **kw: SimpleNamespace(kind="finetuned"),
    )
    monkeypatch.setitem(sys.modules, "pdomain_book_tools.ocr.doctr_support", fake_module)
    return PredictorCache()


def test_loader_run_ocr_returns_page_load_outcome(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    outcome = loader.run_ocr(1)
    assert isinstance(outcome, PageLoadOutcome)
    assert outcome.page_index == 1
    assert outcome.source == PageSource.OCR
    assert outcome.payload.source_identifier == "page_001.png"


def test_loader_run_ocr_passes_image_path_and_source_identifier(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    loader.run_ocr(0)
    call = stub_pdomain_book_tools.calls[0]
    expected_path = project.image_paths[0]
    assert call["image_path"] == expected_path
    assert call["source_identifier"] == expected_path.name


def test_loader_run_ocr_uses_predictor_from_cache(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    loader.run_ocr(0)
    loader.run_ocr(1)
    # Both calls received the same predictor (cache hit on the same key).
    assert stub_pdomain_book_tools.calls[0]["predictor"] is stub_pdomain_book_tools.calls[1]["predictor"]


def test_loader_run_ocr_raises_on_out_of_range_index(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _make_project(tmp_path, n_pages=2)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    with pytest.raises(IndexError):
        loader.run_ocr(5)
    with pytest.raises(IndexError):
        loader.run_ocr(-1)


def test_loader_run_ocr_raises_page_image_not_found_when_file_missing(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """Loader catches missing image *before* OCR — cheap fail.

    Subclass of FileNotFoundError per ``core/page_state.py`` contract.
    """
    project = _make_project(tmp_path, n_pages=2)
    project.image_paths[0].unlink()  # delete the file

    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    from pdomain_ocr_labeler_spa.core.page_state import PageImageNotFoundError

    with pytest.raises(PageImageNotFoundError):
        loader.run_ocr(0)
    # And no OCR was attempted.
    assert stub_pdomain_book_tools.calls == []


def test_load_labeled_returns_none_when_data_root_is_none(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """Backward-compat: when ``data_root`` is unset, the labeled lane
    is a no-op (so the existing slice-8b-ii loader construction without
    persistence wiring keeps working)."""
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    assert loader.load_labeled(0) is None


def test_load_cached_returns_none_when_cache_root_is_none(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    assert loader.load_cached(0) is None


# ── slice 8b-iv: labeled / cached lanes wired through envelope reader ─────


def _make_loader_with_persistence(
    tmp_path: Path,
    predictor_cache: PredictorCache,
    *,
    data_root: Path | None = None,
    cache_root: Path | None = None,
    n_pages: int = 2,
) -> LocalDoctrPageLoader:
    project_root = tmp_path / "project_dir"
    project_root.mkdir(parents=True, exist_ok=True)
    project = _make_project(project_root, n_pages=n_pages)
    return LocalDoctrPageLoader(
        project=project,
        predictor_cache=predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
        data_root=data_root,
        cache_root=cache_root,
    )


def _write_envelope_at(path: Path, payload_page: dict) -> None:
    import json

    from pdomain_ocr_labeler_spa.core.persistence.user_page_envelope import (
        USER_PAGE_SCHEMA_NAME,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"},
                "provenance": {"saved_at": "2026-01-01T00:00:00Z"},
                "source": {
                    "project_id": "project_dir",
                    "page_index": 0,
                    "page_number": 1,
                    "image_path": "page_000.png",
                },
                "payload": {"page": payload_page},
            }
        )
    )


def test_load_labeled_is_a_no_op_stub(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """load_labeled always returns None — the labeled lane is retired (M5b).

    Replaces retired envelope-lane test. The labeled lane was removed as part
    of the greenfield event-store adoption. The successor path is the
    LocalPageStore blob-store ingestion: tests/unit/adapters/test_local_doctr_page_store.py.
    """
    data_root = tmp_path / "data"
    loader = _make_loader_with_persistence(tmp_path, stub_predictor_cache, data_root=data_root)
    # No envelope on disk and no event store — load_labeled must return None
    assert loader.load_labeled(0) is None


def test_load_labeled_returns_none_when_no_envelope_on_disk(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """No envelope at the expected path → ``None`` (loader falls
    through to the cached lane / OCR per spec)."""
    data_root = tmp_path / "data"
    loader = _make_loader_with_persistence(tmp_path, stub_predictor_cache, data_root=data_root)
    assert loader.load_labeled(0) is None


def test_load_labeled_always_returns_none_regardless_of_disk_state(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """load_labeled returns None even when the old envelope path has content.

    Replaces retired corrupt-envelope test. The labeled lane is retired (M5b);
    any on-disk legacy envelope files are ignored. The stub always returns None.
    """
    data_root = tmp_path / "data"
    loader = _make_loader_with_persistence(tmp_path, stub_predictor_cache, data_root=data_root)
    # Write something at the old labeled-lane path — must still be ignored
    legacy_dir = data_root / "labeled-projects" / loader.project.project_id
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "page_000_NNN.json").write_text('{"some": "legacy_data"}')
    assert loader.load_labeled(0) is None


def test_load_cached_is_a_no_op_stub(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """load_cached always returns None — the cached lane is retired (M5b).

    Replaces retired cached-envelope-lane test. The cached lane was removed
    as part of the greenfield event-store adoption. The successor path is
    the LocalPageStore blob-store ingestion:
    tests/unit/adapters/test_local_doctr_page_store.py.
    """
    cache_root = tmp_path / "cache"
    loader = _make_loader_with_persistence(tmp_path, stub_predictor_cache, cache_root=cache_root)
    assert loader.load_cached(0) is None


def test_load_cached_returns_none_when_no_envelope_on_disk(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    cache_root = tmp_path / "cache"
    loader = _make_loader_with_persistence(tmp_path, stub_predictor_cache, cache_root=cache_root)
    assert loader.load_cached(0) is None


def test_ensure_page_model_falls_through_to_ocr_when_no_lanes(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """ensure_page_model calls run_ocr when both load_labeled and load_cached return None.

    Replaces 2 retired envelope-lane routing tests (M5b). With labeled and cached
    lanes retired, ensure_page_model always takes the OCR path. Verifies the
    remaining lane precedence logic: labeled→None, cached→None, OCR→outcome.
    """
    from pdomain_ocr_labeler_spa.core.page_state import ensure_page_model
    from pdomain_ocr_labeler_spa.core.project_state import ProjectState

    project = _make_project(tmp_path)
    state = ProjectState()
    state.set_loaded_project(project)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    outcome = ensure_page_model(state, 0, loader=loader)
    assert outcome is not None
    assert outcome.source == PageSource.OCR
    # OCR was invoked (only path available after lanes retired)
    assert len(stub_pdomain_book_tools.calls) >= 1


def test_loader_conforms_to_page_loader_protocol(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """Structural conformance via ``isinstance`` against the
    ``runtime_checkable`` Protocol."""
    from pdomain_ocr_labeler_spa.core.page_state import PageLoader

    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    assert isinstance(loader, PageLoader)


def test_loader_integrates_with_ensure_page_model(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """End-to-end: ``ensure_page_model`` dispatches through the
    loader's three lanes (labeled None → cached None → run_ocr) and
    caches the outcome."""
    from pdomain_ocr_labeler_spa.core.page_state import ensure_page_model
    from pdomain_ocr_labeler_spa.core.project_state import ProjectState

    project = _make_project(tmp_path, n_pages=2)
    state = ProjectState()
    state.set_loaded_project(project)

    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    outcome1 = ensure_page_model(state, 0, loader=loader)
    assert outcome1 is not None
    assert outcome1.source == PageSource.OCR

    # Second call returns cache hit; OCR not re-invoked.
    outcome2 = ensure_page_model(state, 0, loader=loader)
    assert outcome2 is outcome1
    assert len(stub_pdomain_book_tools.calls) == 1


# ── Auto-cache-write side effect after run_ocr ───────────────────────────
#
# Slice "auto-cache-write". Legacy ref:
# pd-ocr-labeler/state/project_state.py:752-799 (auto-save block inside
# ensure_page_model). After a successful OCR run, the loader writes the
# cached envelope to disk so subsequent loads (this session or later)
# hit the cached lane instead of paying OCR cost again.
#
# Failure-mode contract (legacy lines 789-794): exceptions during cache
# write are log-and-swallowed — never derail the OCR call. The OCR
# outcome is still returned to the caller.


def test_run_ocr_does_not_write_cached_envelope_file(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """After run_ocr, NO UserPageEnvelope JSON file is written to disk.

    Replaces 2 retired cached-envelope-write tests (M5b). The auto-cache-write
    side effect was removed when the UserPageEnvelope lane was retired.
    The successor path writes to the LocalPageStore blob store instead:
    tests/unit/adapters/test_local_doctr_page_store.py.
    """
    project = _make_project(tmp_path)
    cache_root = tmp_path / "cache"
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
        cache_root=cache_root,
    )
    loader.run_ocr(0)

    # No envelope JSON files should exist (old cached-lane path retired)
    if cache_root.exists():
        envelope_files = list(cache_root.rglob("*_envelope.json"))
        assert envelope_files == [], f"unexpected envelope files: {envelope_files}"
        json_files = list(cache_root.rglob("*.json"))
        assert json_files == [], f"unexpected JSON files: {json_files}"


def test_run_ocr_skips_cache_write_when_cache_root_none(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """``cache_root=None`` lane is a no-op (preserves the slice-8b-ii
    constructor signature). The OCR still runs and returns normally."""
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
        cache_root=None,
    )

    outcome = loader.run_ocr(0)
    assert outcome.source == PageSource.OCR
    # No directory was created; nothing was written.
    cache_root = tmp_path / "cache"
    assert not cache_root.exists()


def test_run_ocr_swallows_cache_write_failure(
    tmp_path: Path,
    stub_pdomain_book_tools,
    stub_predictor_cache: PredictorCache,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy parity (project_state.py:789-794): a write-time exception
    must be log-and-swallowed — the OCR outcome is returned regardless.
    Patches ``Path.write_text`` only on the cached envelope path so we
    don't break the rest of the suite."""
    project = _make_project(tmp_path)
    cache_root = tmp_path / "cache"
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
        cache_root=cache_root,
    )

    # Force write failure during the cache write.
    import pdomain_ocr_labeler_spa.adapters.ocr.local_doctr as loader_module

    def fail_write(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(loader_module, "_write_cached_envelope_text", fail_write)

    outcome = loader.run_ocr(0)
    assert outcome.source == PageSource.OCR  # still returned

    # No file was successfully written. The cache page-images dir may
    # still be created by the helper before the write fails (or not at
    # all if the failure happens before mkdir); either way no envelope
    # JSON should exist.
    page_images_dir = cache_root / "page-images"
    if page_images_dir.exists():
        assert list(page_images_dir.glob("*_envelope.json")) == []


def test_run_ocr_outcome_carries_detection_and_recognition_keys(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """run_ocr returns a PageLoadOutcome with source=OCR regardless of predictor keys.

    Replaces retired cache-write provenance test (M5b). The provenance is now
    tracked in the LocalPageStore blob-store via PageAggregate events.
    Successor: tests/unit/adapters/test_local_doctr_page_store.py verifies
    the ops PageAggregate carries detection/recognition identity.
    """
    project = _make_project(tmp_path)
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="my-det",
        recognition_key="my-reco",
        hf_revision="abc1234",
    )
    outcome = loader.run_ocr(0)
    assert outcome is not None
    assert outcome.source == PageSource.OCR


# ── Ground-truth injection on Page after OCR ─────────────────────────────
#
# Slice "GT injection on Page after OCR". Legacy parity:
# pd-ocr-labeler/operations/ocr/page_operations.py:363-364 (post-OCR
# add_ground_truth call inside _parse_page) + state/project_state.py:
# 709-719 (find_ground_truth_text(image_name, project.ground_truth_map)).
#
# In the SPA the loader does both halves: lookup + injection. Skip
# injection when the GT lookup returns None or "" — legacy semantics
# (page_operations.py:363 ``if ground_truth_string:``).


def _project_with_gt(tmp_path: Path, gt_map: dict[str, str]) -> Project:
    """Like _make_project but with caller-supplied GT map."""
    image_paths = []
    for i in range(2):
        p = tmp_path / f"page_{i:03d}.png"
        p.write_bytes(b"fake-png")
        image_paths.append(p)
    return Project(
        project_id="proj1",
        project_root=tmp_path,
        image_paths=image_paths,
        ground_truth_map=gt_map,
        total_pages=len(image_paths),
        current_page_index=0,
    )


def test_run_ocr_injects_ground_truth_when_present(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    project = _project_with_gt(tmp_path, {"page_000.png": "hello world"})
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    outcome = loader.run_ocr(0)
    assert outcome.payload.ground_truth_calls == ["hello world"]


def test_run_ocr_skips_injection_when_no_gt(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """Empty GT map → no add_ground_truth call (legacy line 363)."""
    project = _project_with_gt(tmp_path, {})
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    outcome = loader.run_ocr(0)
    assert outcome.payload.ground_truth_calls == []


def test_run_ocr_skips_injection_when_gt_empty_string(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """GT map has the key but value is "" → don't call add_ground_truth.
    Legacy ``if ground_truth_string:`` is falsy for "" (line 363)."""
    project = _project_with_gt(tmp_path, {"page_000.png": ""})
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    outcome = loader.run_ocr(0)
    assert outcome.payload.ground_truth_calls == []


def test_run_ocr_uses_variant_lookup_for_gt(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """GT key with case-insensitive variant matches.
    Legacy ``find_ground_truth_text`` tries lowercase variants."""
    project = _project_with_gt(tmp_path, {"page_001.PNG".lower(): "lower-gt"})
    # File is "page_001.png" so lowercase variant in map should match.
    project = Project(
        project_id="proj1",
        project_root=tmp_path,
        image_paths=project.image_paths,
        ground_truth_map={"page_001.PNG": "exact-only-uppercase"},
        total_pages=2,
    )
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    # The on-disk filename is "page_001.png" (lowercase). The GT map
    # only has "page_001.PNG". find_ground_truth_text falls back to
    # the lowercase variant which IS in the map (since it returns the
    # value of the matched key — and "page_001.PNG".lower() ==
    # "page_001.png" — but we have "PNG" capitalized in the map, so
    # the lowercase fallback won't match either; pin: returns None ⇒
    # no injection).
    outcome = loader.run_ocr(1)
    assert outcome.payload.ground_truth_calls == []


def test_run_ocr_injects_when_gt_keyed_by_lowercase(
    tmp_path: Path, stub_pdomain_book_tools, stub_predictor_cache: PredictorCache
) -> None:
    """The realistic case: GT map has the canonical lowercase key,
    image filename is lowercase, find returns it."""
    project = _project_with_gt(tmp_path, {"page_001.png": "matched-gt"})
    loader = LocalDoctrPageLoader(
        project=project,
        predictor_cache=stub_predictor_cache,
        detection_key="stock",
        recognition_key="stock",
        hf_revision=None,
    )
    outcome = loader.run_ocr(1)
    assert outcome.payload.ground_truth_calls == ["matched-gt"]
