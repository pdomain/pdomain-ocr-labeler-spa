"""Tests for core/persistence/lanes.py — three-lane model (#221).

Spec: docs/specs/2026-05-12-persistence-design.md + issue #221.

Acceptance (issue #221):
- Source lane is read-only; writes raise SourceLaneReadOnlyError.
- Labeled lane written only on explicit Save Page / Save Project.
- Cached lane written after every mutation.
- Read-precedence follows labeled → cached → OCR → fallback order.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.persistence.lanes import (
    LaneReadResult,
    LaneResolver,
    SourceLaneReadOnlyError,
)
from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
    UserPageEnvelope,
    parse_envelope,
)

# ── Minimal envelope fixture ──────────────────────────────────────────────────


def _make_minimal_envelope(project_id: str = "test-proj", page_index: int = 0) -> UserPageEnvelope:
    """Construct a minimal valid UserPageEnvelope for testing via parse_envelope."""
    raw: dict = {
        "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.1"},
        "provenance": {
            "saved_at": "",
            "saved_by": "Save Page",
            "source_lane": "labeled",
            "app": {},
            "toolchain": {},
            "ocr": {},
        },
        "source": {
            "project_id": project_id,
            "page_index": page_index,
            "page_number": page_index + 1,
            "image_path": f"page_{page_index + 1:03d}.png",
        },
        "payload": {"page": {"lines": []}},
    }
    return parse_envelope(raw)


# ── Resolver construction ──────────────────────────────────────────────────────


def test_lane_resolver_constructs_without_io(tmp_path: Path) -> None:
    """LaneResolver can be constructed without performing any I/O."""
    resolver = LaneResolver(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        project_id="test-proj",
    )
    assert resolver is not None
    # No directories should have been created.
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "cache").exists()


# ── Read-precedence: both lanes miss → None ────────────────────────────────────


def test_load_page_returns_none_when_both_lanes_empty(tmp_path: Path) -> None:
    """When neither labeled nor cached lane has a file, returns None."""
    resolver = LaneResolver(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        project_id="test-proj",
    )
    result = resolver.load_page_from_disk(page_index=0)
    assert result is None


# ── Read-precedence: labeled lane hits first ──────────────────────────────────


def test_load_page_returns_labeled_when_both_exist(tmp_path: Path) -> None:
    """Labeled lane takes precedence over cached when both exist.

    Issue #221: "Read-precedence follows labeled → cached → OCR → fallback".
    """
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    resolver = LaneResolver(data_root=data_root, cache_root=cache_root, project_id="test-proj")

    envelope = _make_minimal_envelope("test-proj", 0)
    # Write to both lanes
    resolver.write_labeled(0, envelope)
    resolver.write_cached(0, envelope)

    result = resolver.load_page_from_disk(0)
    assert result is not None
    assert result.source == "labeled"


def test_load_page_falls_back_to_cached_when_no_labeled(tmp_path: Path) -> None:
    """Falls back to cached lane when labeled lane has no file."""
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    resolver = LaneResolver(data_root=data_root, cache_root=cache_root, project_id="test-proj")

    envelope = _make_minimal_envelope("test-proj", 0)
    resolver.write_cached(0, envelope)

    result = resolver.load_page_from_disk(0)
    assert result is not None
    assert result.source == "cached"


def test_load_page_result_has_envelope(tmp_path: Path) -> None:
    """LaneReadResult contains a valid UserPageEnvelope."""
    data_root = tmp_path / "data"
    cache_root = tmp_path / "cache"
    resolver = LaneResolver(data_root=data_root, cache_root=cache_root, project_id="test-proj")

    envelope = _make_minimal_envelope("test-proj", 2)
    resolver.write_cached(2, envelope)

    result = resolver.load_page_from_disk(2)
    assert isinstance(result, LaneReadResult)
    assert isinstance(result.envelope, UserPageEnvelope)
    assert result.envelope.source.page_index == 2


# ── Labeled lane writes ────────────────────────────────────────────────────────


def test_write_labeled_creates_file(tmp_path: Path) -> None:
    """write_labeled creates the labeled lane envelope file."""
    data_root = tmp_path / "data"
    resolver = LaneResolver(data_root=data_root, cache_root=tmp_path / "cache", project_id="proj1")

    envelope = _make_minimal_envelope("proj1", 0)
    path = resolver.write_labeled(0, envelope)

    assert path.exists()
    assert path.name.endswith(".json")
    # Verify the file contains valid JSON
    data = json.loads(path.read_text())
    assert data["schema"]["name"] == "pd_ocr_labeler.user_page"


def test_write_labeled_creates_parent_dir(tmp_path: Path) -> None:
    """write_labeled creates parent directories when they don't exist."""
    data_root = tmp_path / "data"
    resolver = LaneResolver(data_root=data_root, cache_root=tmp_path / "cache", project_id="new-proj")
    envelope = _make_minimal_envelope("new-proj", 5)
    path = resolver.write_labeled(5, envelope)

    assert path.parent.is_dir()
    assert path.exists()


def test_write_labeled_under_labeled_projects(tmp_path: Path) -> None:
    """write_labeled path is under data_root/labeled-projects/<project_id>/."""
    data_root = tmp_path / "data"
    resolver = LaneResolver(data_root=data_root, cache_root=tmp_path / "cache", project_id="myp")

    envelope = _make_minimal_envelope("myp", 0)
    path = resolver.write_labeled(0, envelope)

    assert str(path).startswith(str(data_root / "labeled-projects" / "myp"))


def test_write_labeled_is_atomic(tmp_path: Path) -> None:
    """write_labeled uses atomic write (no .tmp leftover)."""
    data_root = tmp_path / "data"
    resolver = LaneResolver(data_root=data_root, cache_root=tmp_path / "cache", project_id="atest")
    envelope = _make_minimal_envelope("atest", 0)
    path = resolver.write_labeled(0, envelope)

    # No .tmp file should remain
    tmp_candidate = path.with_suffix(".tmp")
    assert not tmp_candidate.exists()


# ── Cached lane writes ─────────────────────────────────────────────────────────


def test_write_cached_creates_file(tmp_path: Path) -> None:
    """write_cached creates the cached lane envelope file."""
    cache_root = tmp_path / "cache"
    resolver = LaneResolver(data_root=tmp_path / "data", cache_root=cache_root, project_id="cp1")
    envelope = _make_minimal_envelope("cp1", 0)
    resolver.write_cached(0, envelope)

    cache_dir = cache_root / "page-images"
    files = list(cache_dir.glob("*.json"))
    assert len(files) == 1
    assert "_envelope.json" in files[0].name


def test_write_cached_filename_has_envelope_suffix(tmp_path: Path) -> None:
    """Cached lane filename has _envelope.json suffix (SPA-specific, D-003)."""
    cache_root = tmp_path / "cache"
    resolver = LaneResolver(data_root=tmp_path / "data", cache_root=cache_root, project_id="myproj")
    envelope = _make_minimal_envelope("myproj", 0)
    resolver.write_cached(0, envelope)

    files = list((cache_root / "page-images").glob("*"))
    assert any("_envelope.json" in f.name for f in files)


def test_write_cached_does_not_raise_on_io_error(tmp_path: Path, monkeypatch) -> None:
    """write_cached swallows OSError — failed cache write must not propagate.

    Spec: 'Cached lane writes swallow I/O errors (WARNING log only)'.
    """
    from pd_ocr_labeler_spa.core.persistence import atomic

    def _fail(*_args, **_kwargs) -> None:
        raise OSError("simulated disk full")

    monkeypatch.setattr(atomic, "write_json_atomic", _fail)

    cache_root = tmp_path / "cache"
    resolver = LaneResolver(data_root=tmp_path / "data", cache_root=cache_root, project_id="ep")
    envelope = _make_minimal_envelope("ep", 0)
    # Must NOT raise
    resolver.write_cached(0, envelope)


def test_write_cached_overwrites_on_repeat(tmp_path: Path) -> None:
    """write_cached is a singleton — repeated write overwrites the previous.

    Spec: "Cached envelopes are singletons".
    """
    cache_root = tmp_path / "cache"
    resolver = LaneResolver(data_root=tmp_path / "data", cache_root=cache_root, project_id="ow")
    env_a = _make_minimal_envelope("ow", 1)
    env_b = _make_minimal_envelope("ow", 1)

    resolver.write_cached(1, env_a)
    resolver.write_cached(1, env_b)

    files = list((cache_root / "page-images").glob("*.json"))
    assert len(files) == 1  # Only one file — singleton overwrite


# ── Source lane read-only guard ────────────────────────────────────────────────


def test_source_lane_read_only_error_subclasses_permission_error() -> None:
    """SourceLaneReadOnlyError subclasses PermissionError."""
    assert issubclass(SourceLaneReadOnlyError, PermissionError)


def test_write_labeled_raises_for_path_outside_labeled_root(tmp_path: Path) -> None:
    """write_labeled raises SourceLaneReadOnlyError if path escapes labeled-projects/.

    Belt-and-suspenders guard for the source-lane read-only invariant
    (issue #221).
    """
    data_root = tmp_path / "data"
    resolver = LaneResolver(data_root=data_root, cache_root=tmp_path / "cache", project_id="test-proj")
    envelope = _make_minimal_envelope("test-proj", 0)

    # Monkeypatch labeled_envelope_path to return a path outside labeled-projects/
    from pd_ocr_labeler_spa.core.persistence import user_page_envelope as upe

    original = upe.labeled_envelope_path

    def _bad_path(data_root: Path, project_id: str, page_index: int) -> Path:
        # Return a path outside labeled-projects/
        return data_root / "source-projects" / project_id / f"{project_id}_{page_index}.json"

    import pd_ocr_labeler_spa.core.persistence.lanes as lanes_mod

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(lanes_mod, "labeled_envelope_path", _bad_path)
    try:
        with pytest.raises(SourceLaneReadOnlyError):
            resolver.write_labeled(0, envelope)
    finally:
        monkeypatch.setattr(lanes_mod, "labeled_envelope_path", original)
