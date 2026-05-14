"""Path helpers + ``read_envelope_file`` for the user-page envelope.

Spec authority:

- ``docs/architecture/09-persistence.md §1`` lines 19–32 — three on-disk lanes:

  - **Labeled lane**: ``<data_root>/labeled-projects/<project_id>/
    <project_id>_<page:03d>.json`` (D-003 byte-compat with legacy).
  - **Cached lane**: ``<cache_root>/page-images/<project_id>_
    <page:03d>_envelope.json`` (SPA-specific filename with the
    ``_envelope`` suffix, per spec line 28).

- ``docs/architecture/09-persistence.md §2`` lines 79–86 — reader API surface.

Slice 8b-iv ships:

- ``labeled_envelope_path(data_root, project_id, page_index) -> Path``
- ``cached_envelope_path(cache_root, project_id, page_index) -> Path``
- ``read_envelope_file(path) -> UserPageEnvelope | None`` —
  failure-mode-tolerant disk reader (missing / unparsable / wrong-shape
  → ``None``; never raises). Same contract as
  ``persistence/session_state.load_session_state``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pd_ocr_labeler_spa.core.persistence.user_page_envelope import (
    USER_PAGE_SCHEMA_NAME,
    cached_envelope_path,
    labeled_envelope_path,
    read_envelope_file,
)

# ── path derivation: labeled lane ────────────────────────────────────────


def test_labeled_envelope_path_shape(tmp_path: Path) -> None:
    """``<data_root>/labeled-projects/<project_id>/<project_id>_<page:03d>.json``
    per spec §1 line 22."""
    data_root = tmp_path / "data"
    p = labeled_envelope_path(data_root, project_id="the_four_men", page_index=0)
    assert p == data_root / "labeled-projects" / "the_four_men" / "the_four_men_001.json"


def test_labeled_envelope_path_uses_one_based_zero_padded_page_number(
    tmp_path: Path,
) -> None:
    """Filename uses ``<page:03d>`` where ``page = page_index + 1``
    (legacy parity — ``operations/ocr/page_operations.py:430`` does
    ``page_number = getattr(page_obj, "index", 0) + 1`` then formats
    ``{:03d}``)."""
    p = labeled_envelope_path(tmp_path, project_id="p", page_index=4)
    assert p.name == "p_005.json"


def test_labeled_envelope_path_pads_to_three_digits(tmp_path: Path) -> None:
    p = labeled_envelope_path(tmp_path, project_id="p", page_index=99)
    assert p.name == "p_100.json"


def test_labeled_envelope_path_does_not_pad_when_above_three_digits(
    tmp_path: Path,
) -> None:
    """``%03d`` is a *minimum* width — page 1000 stays four digits."""
    p = labeled_envelope_path(tmp_path, project_id="p", page_index=999)
    assert p.name == "p_1000.json"


# ── path derivation: cached lane ─────────────────────────────────────────


def test_cached_envelope_path_shape(tmp_path: Path) -> None:
    """``<cache_root>/page-images/<project_id>_<page:03d>_envelope.json``
    per spec §1 line 28."""
    cache_root = tmp_path / "cache"
    p = cached_envelope_path(cache_root, project_id="the_four_men", page_index=0)
    assert p == cache_root / "page-images" / "the_four_men_001_envelope.json"


def test_cached_envelope_path_diverges_from_labeled_filename(
    tmp_path: Path,
) -> None:
    """Critical pin: cached lane MUST use ``_envelope.json`` suffix
    (the spec-pinned divergence from legacy, since legacy treats this
    dir flat alongside its own .json files; the suffix prevents
    legacy/SPA cache writers from overwriting each other)."""
    labeled = labeled_envelope_path(tmp_path, project_id="p", page_index=0)
    cached = cached_envelope_path(tmp_path, project_id="p", page_index=0)
    assert labeled.name == "p_001.json"
    assert cached.name == "p_001_envelope.json"
    assert labeled.name != cached.name


def test_cached_envelope_path_uses_page_images_dirname(tmp_path: Path) -> None:
    """The cache subdir name is ``page-images/`` (legacy parity —
    ``operations/persistence/persistence_paths_operations.py:108``)."""
    p = cached_envelope_path(tmp_path, project_id="p", page_index=0)
    assert p.parent.name == "page-images"


# ── read_envelope_file: failure modes ────────────────────────────────────


def test_read_envelope_missing_returns_none(tmp_path: Path) -> None:
    """Cold-start case — no file on disk yet."""
    assert read_envelope_file(tmp_path / "missing.json") is None


def test_read_envelope_unparsable_returns_none(tmp_path: Path, caplog) -> None:
    """Garbage JSON → ``None`` + DEBUG log (so a corrupt cache doesn't
    crash a page load — the legacy contract per spec §9 lines 32–40
    falls through to OCR)."""
    p = tmp_path / "envelope.json"
    p.write_text("not json {{{")
    with caplog.at_level(logging.DEBUG):
        assert read_envelope_file(p) is None


def test_read_envelope_non_dict_root_returns_none(tmp_path: Path) -> None:
    """A JSON file whose top-level is e.g. an array → ``None``
    (parser would happily run, but the type guard catches it
    upstream — symmetry with session_state)."""
    p = tmp_path / "envelope.json"
    p.write_text("[1, 2, 3]")
    assert read_envelope_file(p) is None


def test_read_envelope_wrong_schema_name_returns_none(tmp_path: Path) -> None:
    """An on-disk JSON file in our lane that's NOT a UserPageEnvelope
    (e.g. a stray ``project.json``) → ``None`` so the loader falls
    through to OCR rather than parsing garbage as if it were a page."""
    p = tmp_path / "envelope.json"
    p.write_text(json.dumps({"schema": {"name": "pd_ocr_labeler.project"}}))
    assert read_envelope_file(p) is None


def test_read_envelope_happy_path(tmp_path: Path) -> None:
    """Round-trip: write a minimal valid envelope, read it back, get
    a populated UserPageEnvelope."""
    p = tmp_path / "envelope.json"
    payload_dict = {
        "schema": {"name": USER_PAGE_SCHEMA_NAME, "version": "2.1"},
        "provenance": {"saved_at": "2026-01-01T00:00:00Z"},
        "source": {
            "project_id": "p",
            "page_index": 0,
            "page_number": 1,
            "image_path": "001.png",
        },
        "payload": {"page": {"index": 0, "name": "001.png"}},
    }
    p.write_text(json.dumps(payload_dict))
    env = read_envelope_file(p)
    assert env is not None
    assert env.source.project_id == "p"
    assert env.source.page_index == 0
    assert env.payload.page == {"index": 0, "name": "001.png"}
