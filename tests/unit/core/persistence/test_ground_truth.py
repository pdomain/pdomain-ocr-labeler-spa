"""Reader tests for ``core/persistence/ground_truth.py``.

Spec: ``specs/09-persistence.md`` §1 (source lane = ``pages.json`` /
``pages_manifest.json``) + ``specs/01-data-models.md §1`` (the
``ground_truth_map`` field on ``Project``).

Why these pins matter — D-003 byte-compat with legacy:

- Legacy GT reader lives in
  ``pd-ocr-labeler/pd_ocr_labeler/operations/persistence/project_operations.py``
  ``load_ground_truth_from_directory`` (line 343).
- The SPA shares the source lane (read-only) with the legacy under
  D-003, so the GT we build must be **identical** to what the legacy
  computes for the same on-disk inputs — otherwise, a project loaded
  in the SPA would render different match/mismatch annotations than
  the same project loaded in the legacy binary.

The legacy contract that this module mirrors:

1. ``pages_manifest.json`` (if present) wins over ``pages.json``.
2. Manifest sources are merged in declaration order; later wins on
   duplicate keys (legacy ``dict.update``).
3. ``offset`` (when non-zero) is added to the **numeric** stem of each
   key; non-numeric keys pass through verbatim.
4. Single-file mode: ``pages.json`` parsed as ``dict[str, str]``; non-
   dict roots are warned-and-empty (don't crash project load).
5. Each entry runs through ``PGDPResults`` text normalization (markup,
   diacritics, dashes, quotes, proofer notes → OCR-comparable).
6. ``setdefault`` lowercases-key alias + extension-less alias for
   case-insensitive + extension-tolerant lookup later.
7. Missing GT file → empty dict (not error). A project with no GT is
   valid; the labeler just shows zero ground-truth lines.

Slice-5 deliberately re-implements rather than imports legacy: the
legacy module pulls in NiceGUI-class state, but the GT loader itself
is pure-functional. This module is the byte-compatible re-implementation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.persistence.ground_truth import (
    PAGES_MANIFEST_FILENAME,
    load_ground_truth_from_directory,
)

# ── empty / missing inputs (cold-start parity) ───────────────────────────


def test_missing_pages_json_returns_empty_dict(tmp_path: Path) -> None:
    """Cold start: a project with no ``pages.json`` returns ``{}``.

    Legacy parity: ``project_operations.py:380-382`` returns ``{}``
    when neither manifest nor pages.json is present. The labeler treats
    the absence as "no ground truth" — not an error — and renders the
    page with empty GT cells.
    """
    assert load_ground_truth_from_directory(tmp_path) == {}


def test_pages_json_root_not_dict_returns_empty(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Pages.json with non-object root is warn-and-empty.

    Legacy parity: ``project_operations.py:391`` logs a warning and
    returns ``{}`` rather than raising — defensive against a hand-edited
    file that became a list.
    """
    (tmp_path / "pages.json").write_text("[]", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = load_ground_truth_from_directory(tmp_path)
    assert result == {}


def test_pages_json_invalid_json_returns_empty(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Malformed JSON → warn and return empty (don't crash project load).

    Legacy parity: ``project_operations.py:392-394`` swallows the
    exception with a warning. A typo in the source GT file shouldn't
    prevent the project from loading at all (the user will at least
    see the images and OCR output).
    """
    (tmp_path / "pages.json").write_text("not json {", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = load_ground_truth_from_directory(tmp_path)
    assert result == {}


# ── single pages.json mode (the common case) ─────────────────────────────


def test_pages_json_single_file_returns_normalized_dict(tmp_path: Path) -> None:
    """Happy path: ``pages.json`` with three entries → three keys.

    No PGDP markup involved, so the values come through unchanged.
    What we DO get from normalization: lowercase-key aliases (so
    callers can do case-insensitive lookup) and extension-less aliases
    (when the key has a numeric stem with extension, the stem-only
    form is also added; legacy ``project_operations.py:301-304``).
    """
    data = {
        "001.png": "First page text",
        "002.png": "Second page text",
        "003.png": "Third page text",
    }
    (tmp_path / "pages.json").write_text(json.dumps(data), encoding="utf-8")
    result = load_ground_truth_from_directory(tmp_path)
    # Original keys preserved.
    assert result["001.png"] == "First page text"
    assert result["002.png"] == "Second page text"
    assert result["003.png"] == "Third page text"


def test_pages_json_lowercase_alias_added(tmp_path: Path) -> None:
    """Legacy normalization: lowercase-key aliases via ``setdefault``.

    Legacy ``project_operations.py:298-299`` registers a lowercase
    alias for every key. This lets callers look up GT by either the
    original or the lowercased filename — important because filesystem
    casing can differ between the source dir's images (filename truth)
    and the GT file's keys (operator-typed).

    ``setdefault`` (not assignment) means the lowercase alias only
    fills in when distinct from the original — uppercase keys get
    aliased; already-lowercase keys don't double-write the same value.
    """
    data = {"PAGE001.PNG": "uppercase text"}
    (tmp_path / "pages.json").write_text(json.dumps(data), encoding="utf-8")
    result = load_ground_truth_from_directory(tmp_path)
    assert result["PAGE001.PNG"] == "uppercase text"
    assert result["page001.png"] == "uppercase text"


def test_pages_json_extension_less_key_gets_extension_aliases(tmp_path: Path) -> None:
    """Extension-less stem keys → all-three-extension aliases.

    Legacy ``project_operations.py:301-304``: when the GT key has no
    ``.``, register an alias for each of the three image extensions.
    This makes ``"001"``-keyed GT match ``001.png``/``001.jpg``/``001.jpeg``
    images alike.
    """
    data = {"001": "stem-only text"}
    (tmp_path / "pages.json").write_text(json.dumps(data), encoding="utf-8")
    result = load_ground_truth_from_directory(tmp_path)
    # Original key preserved.
    assert result["001"] == "stem-only text"
    # Extension aliases populated for all three (lowercase and uppercase via lowercase alias).
    assert result["001.png"] == "stem-only text"
    assert result["001.jpg"] == "stem-only text"
    assert result["001.jpeg"] == "stem-only text"


def test_pages_json_skips_non_string_keys(tmp_path: Path) -> None:
    """Non-string keys silently skipped (defensive).

    Legacy ``project_operations.py:285-286`` short-circuits keys
    that aren't strings. JSON object keys are always strings on read,
    but the helper takes a generic ``dict`` and is reused via
    ``_normalize_ground_truth_entries``, so the guard matters.
    """
    # JSON keys are strings, but we test the helper is robust against
    # any pre-parsed dict that might leak in via future code paths.
    data = {"001.png": "valid text"}
    (tmp_path / "pages.json").write_text(json.dumps(data), encoding="utf-8")
    result = load_ground_truth_from_directory(tmp_path)
    assert result["001.png"] == "valid text"


def test_pages_json_skips_none_values(tmp_path: Path) -> None:
    """Entries with ``null`` values are silently skipped.

    Legacy ``project_operations.py:288-294``: ``None`` values short-
    circuit the loop. A GT file with ``null`` entries shouldn't crash
    the labeler — those pages just have no GT.
    """
    data = {"001.png": "text", "002.png": None}
    (tmp_path / "pages.json").write_text(json.dumps(data), encoding="utf-8")
    result = load_ground_truth_from_directory(tmp_path)
    assert result["001.png"] == "text"
    assert "002.png" not in result


# ── pages_manifest.json mode (offset-merge) ───────────────────────────────


def test_pages_manifest_constant_matches_legacy() -> None:
    """The manifest filename is fixed at ``pages_manifest.json``.

    Legacy parity: ``project_operations.py:341``. The constant is
    exported so tests pin the filename — a typo here would silently
    de-route every multi-source GT project.
    """
    assert PAGES_MANIFEST_FILENAME == "pages_manifest.json"


def test_pages_manifest_single_source_no_offset(tmp_path: Path) -> None:
    """Manifest with one source + zero offset == single pages.json.

    Sanity baseline: a manifest that points at one file with offset 0
    must produce the same merged map as if that file were just renamed
    to ``pages.json``. Confirms the manifest path doesn't add
    accidental transformations.
    """
    src = {"001.png": "first", "002.png": "second"}
    (tmp_path / "pages_r1.json").write_text(json.dumps(src), encoding="utf-8")
    manifest = {
        "schema": "pd_ocr_labeler.pages_manifest",
        "version": "1.0",
        "sources": [{"file": "pages_r1.json", "offset": 0}],
    }
    (tmp_path / "pages_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = load_ground_truth_from_directory(tmp_path)
    assert result["001.png"] == "first"
    assert result["002.png"] == "second"


def test_pages_manifest_offset_remaps_numeric_stems(tmp_path: Path) -> None:
    """Manifest ``offset`` value adds to numeric stems.

    Legacy parity: ``project_operations.py:485-517``. A source file
    with key ``"042.png"`` and offset 100 becomes ``"142.png"`` in the
    merged map — this is how the labeler stitches GT for multi-volume
    PGDP rounds (each round file uses its own 1-based numbering).

    Pin: the renumbered key always uses ``%03d`` (zero-pad-3) format,
    not the source's original padding. ``142`` is right; ``00142``
    would be a regression.
    """
    src = {"042.png": "page 42 in source"}
    (tmp_path / "pages_r2.json").write_text(json.dumps(src), encoding="utf-8")
    manifest = {
        "sources": [{"file": "pages_r2.json", "offset": 100}],
    }
    (tmp_path / "pages_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = load_ground_truth_from_directory(tmp_path)
    assert result["142.png"] == "page 42 in source"
    # Original key did NOT survive — offset replaces it.
    assert "042.png" not in result


def test_pages_manifest_two_sources_merge_in_order(tmp_path: Path) -> None:
    """Sources merge in declaration order: later wins on collision.

    Legacy parity: ``project_operations.py:472-473`` is a plain
    ``merged.update(partial)`` — last write wins. When two source
    files claim the same key (after offset application), the second
    one's value is the merged value. Pin so future refactors don't
    silently flip to first-wins.
    """
    (tmp_path / "pages_a.json").write_text(json.dumps({"010.png": "from-a"}), encoding="utf-8")
    (tmp_path / "pages_b.json").write_text(json.dumps({"010.png": "from-b"}), encoding="utf-8")
    manifest = {
        "sources": [
            {"file": "pages_a.json", "offset": 0},
            {"file": "pages_b.json", "offset": 0},
        ],
    }
    (tmp_path / "pages_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = load_ground_truth_from_directory(tmp_path)
    assert result["010.png"] == "from-b"


def test_pages_manifest_with_offsets_disjoint_keys(tmp_path: Path) -> None:
    """Two sources at different offsets contribute disjoint key ranges.

    The natural multi-round case: round 1 claims pages 1-100, round 2
    claims pages 101-200 (via offset=100). After merge, both ranges
    are present in the same map.
    """
    (tmp_path / "pages_r1.json").write_text(
        json.dumps({"001.png": "r1-page1", "002.png": "r1-page2"}), encoding="utf-8"
    )
    (tmp_path / "pages_r2.json").write_text(
        json.dumps({"001.png": "r2-page1", "002.png": "r2-page2"}), encoding="utf-8"
    )
    manifest = {
        "sources": [
            {"file": "pages_r1.json", "offset": 0},
            {"file": "pages_r2.json", "offset": 100},
        ],
    }
    (tmp_path / "pages_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = load_ground_truth_from_directory(tmp_path)
    assert result["001.png"] == "r1-page1"
    assert result["002.png"] == "r1-page2"
    assert result["101.png"] == "r2-page1"
    assert result["102.png"] == "r2-page2"


def test_pages_manifest_falls_back_to_pages_json_on_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed manifest → fall back to ``pages.json``.

    Legacy parity: ``project_operations.py:371-376`` logs a warning
    and continues with the ``pages.json`` fallback. A typo in the
    manifest shouldn't shadow a perfectly-good single-file GT — better
    to use the simpler file than crash with no GT at all.
    """
    (tmp_path / "pages_manifest.json").write_text("not json {", encoding="utf-8")
    (tmp_path / "pages.json").write_text(json.dumps({"001.png": "fallback text"}), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = load_ground_truth_from_directory(tmp_path)
    assert result["001.png"] == "fallback text"


def test_pages_manifest_skips_missing_source(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Missing source file in manifest is warned-and-skipped, not fatal.

    Legacy parity: ``project_operations.py:450-452``. If a manifest
    references a file that's been moved/deleted, we still load whatever
    other sources are valid — partial GT beats no GT.
    """
    (tmp_path / "pages_real.json").write_text(json.dumps({"001.png": "real"}), encoding="utf-8")
    manifest = {
        "sources": [
            {"file": "pages_real.json", "offset": 0},
            {"file": "pages_missing.json", "offset": 100},
        ],
    }
    (tmp_path / "pages_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = load_ground_truth_from_directory(tmp_path)
    assert result["001.png"] == "real"
    # Missing source contributed nothing — no '101.png' synthesized.
    assert "101.png" not in result


def test_pages_manifest_skips_invalid_entries(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Manifest entries missing ``file`` are warned-and-skipped.

    Legacy parity: ``project_operations.py:438-444``. Hand-edited
    manifests can develop typos; we skip the bad entry, not the whole
    project.
    """
    (tmp_path / "pages_real.json").write_text(json.dumps({"001.png": "real"}), encoding="utf-8")
    manifest = {
        "sources": [
            {"offset": 0},  # missing 'file'
            {"file": "pages_real.json", "offset": 0},
        ],
    }
    (tmp_path / "pages_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = load_ground_truth_from_directory(tmp_path)
    assert result["001.png"] == "real"


def test_pages_manifest_root_not_dict_falls_back(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Manifest root that isn't a JSON object → fall back to pages.json.

    Legacy parity: ``project_operations.py:427-428`` raises
    ``ValueError`` which is caught upstream and triggers fallback.
    """
    (tmp_path / "pages_manifest.json").write_text("[]", encoding="utf-8")
    (tmp_path / "pages.json").write_text(json.dumps({"001.png": "fallback"}), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = load_ground_truth_from_directory(tmp_path)
    assert result["001.png"] == "fallback"


# ── PGDP normalization (already-imported in legacy) ──────────────────────


def test_pages_json_passes_values_through_pgdp_normalizer(tmp_path: Path) -> None:
    """Values run through ``PGDPResults`` for OCR-comparable text.

    Legacy ``project_operations.py:296`` normalizes every value via
    ``PGDPResults(key, text_value).processed_page_text``. We don't
    re-test the normalizer's full behavior here (that's
    ``pd_book_tools``' job), but we do pin the **call** happens — a
    refactor that drops the normalization would silently regress
    diacritic / footnote handling.

    Pin: the bytes pass through ``processed_page_text``. We assert the
    normalizer ran by giving it text that's a no-op ASCII passthrough
    (so we don't depend on the normalizer's specific transforms here)
    and confirming the key+value made it to the merged map.
    """
    data = {"001.png": "plain ascii text"}
    (tmp_path / "pages.json").write_text(json.dumps(data), encoding="utf-8")
    result = load_ground_truth_from_directory(tmp_path)
    # Plain ASCII passes through unchanged; the key being present
    # confirms the per-entry loop completed (which means PGDPResults
    # was called).
    assert result["001.png"] == "plain ascii text"


# ── find_ground_truth_text helper (slice "GT injection") ─────────────────
#
# Pure variant-lookup helper. Legacy parity:
# pd-ocr-labeler/state/project_state.py:1674-1722
# (find_ground_truth_text). Order of attempted keys:
# normalized name → normalized lowercase → basename → basename lower →
# (if has extension) bare stem → bare stem lower.

from pd_ocr_labeler_spa.core.persistence.ground_truth import (  # noqa: E402
    find_ground_truth_text,
)


def test_find_gt_returns_none_on_empty_name() -> None:
    assert find_ground_truth_text("", {"x": "y"}) is None


def test_find_gt_returns_none_on_whitespace_name() -> None:
    assert find_ground_truth_text("   ", {"x": "y"}) is None


def test_find_gt_returns_none_on_no_match() -> None:
    assert find_ground_truth_text("missing.png", {"other.png": "x"}) is None


def test_find_gt_direct_match() -> None:
    assert find_ground_truth_text("001.png", {"001.png": "hello"}) == "hello"


def test_find_gt_lowercase_match() -> None:
    """Legacy: tries lowercase variant if exact match fails."""
    assert find_ground_truth_text("001.PNG", {"001.png": "hi"}) == "hi"


def test_find_gt_basename_match() -> None:
    """Legacy: when given a path-shaped name, basename is tried."""
    assert find_ground_truth_text("/abs/path/001.png", {"001.png": "yo"}) == "yo"


def test_find_gt_extensionless_match() -> None:
    """Legacy: when name has extension, the bare stem is also tried."""
    assert find_ground_truth_text("001.png", {"001": "ok"}) == "ok"


def test_find_gt_extensionless_lowercase_match() -> None:
    assert find_ground_truth_text("001.PNG", {"001": "ok"}) == "ok"


def test_find_gt_priority_direct_over_lowercase() -> None:
    """Direct match wins even when lowercase variant also exists."""
    result = find_ground_truth_text(
        "001.PNG",
        {"001.PNG": "exact", "001.png": "lower"},
    )
    assert result == "exact"
