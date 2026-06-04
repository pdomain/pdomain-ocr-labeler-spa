"""Integration tests for ``GET /api/projects/{id}/export/styles`` (Lane E1).

Spec authority:
- ``docs/archive/specs/2026-05-12-export-design.md`` lines 43-44, 119-120 —
  "Switching to 'All Validated Pages' fires GET .../export/styles to enumerate
  distinct style labels across saved validated pages" and "must only query
  saved (labeled) page envelopes, not in-memory state".

Parity gap (Lane E1, plan ``docs/plans/2026-06-03-labeler-spa-legacy-parity.md``):
the route was a stub returning ``[]``; legacy populates it from the page's words.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import pdomain_ocr_labeler_spa.api.export as export_api
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[arg-type]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:  # pyright: ignore[reportInvalidTypeForm, reportReturnType]
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c  # pyright: ignore[reportReturnType]


def _make_word(style_labels: list[str]):
    w = MagicMock()
    w.text_style_labels = style_labels
    w.word_labels = ["validated"]
    return w


def _make_page(words):
    page = MagicMock()
    page.words = words
    return page


def test_export_styles_lists_italic_word(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A saved validated page with an italic word yields ``["italic"]``."""
    data_root = tmp_path / "data"
    proj_dir = data_root / "labeled-projects" / "test-project"
    proj_dir.mkdir(parents=True)
    json_path = proj_dir / "test-project_000.json"
    json_path.write_text("{}", encoding="utf-8")

    import pdomain_ocr_labeler_spa.core.jobs.handlers.export as export_mod

    monkeypatch.setattr(export_mod, "_scan_labeled_pages", lambda dr, pid: [json_path])
    monkeypatch.setattr(
        export_mod,
        "_load_page_from_envelope_file",
        lambda p: _make_page([_make_word(["italic"])]),
    )

    resp = client.get("/api/projects/test-project/export/styles")
    assert resp.status_code == 200
    assert resp.json() == ["italic"]


def test_export_styles_distinct_and_sorted(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multiple pages/words collapse to a distinct, sorted label set."""
    data_root = tmp_path / "data"
    proj_dir = data_root / "labeled-projects" / "test-project"
    proj_dir.mkdir(parents=True)
    p0 = proj_dir / "test-project_000.json"
    p1 = proj_dir / "test-project_001.json"
    p0.write_text("{}", encoding="utf-8")
    p1.write_text("{}", encoding="utf-8")

    import pdomain_ocr_labeler_spa.core.jobs.handlers.export as export_mod

    pages = {
        p0: _make_page([_make_word(["small caps"]), _make_word(["italic"])]),
        p1: _make_page([_make_word(["italic"]), _make_word([])]),
    }
    monkeypatch.setattr(export_mod, "_scan_labeled_pages", lambda dr, pid: [p0, p1])
    monkeypatch.setattr(export_mod, "_load_page_from_envelope_file", lambda p: pages[p])

    resp = client.get("/api/projects/test-project/export/styles")
    assert resp.status_code == 200
    assert resp.json() == ["italic", "small caps"]


def test_export_styles_empty_when_no_pages(client: TestClient) -> None:
    """No labeled pages → empty list (unchanged stub behaviour)."""
    resp = client.get("/api/projects/empty-project/export/styles")
    assert resp.status_code == 200
    assert resp.json() == []


def test_export_styles_skips_non_validated_pages(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Styles come only from fully-validated saved pages (parity with WordFilter scope)."""
    data_root = tmp_path / "data"
    proj_dir = data_root / "labeled-projects" / "test-project"
    proj_dir.mkdir(parents=True)
    json_path = proj_dir / "test-project_000.json"
    json_path.write_text("{}", encoding="utf-8")

    import pdomain_ocr_labeler_spa.core.jobs.handlers.export as export_mod

    word = _make_word(["italic"])
    word.word_labels = []  # not validated
    monkeypatch.setattr(export_mod, "_scan_labeled_pages", lambda dr, pid: [json_path])
    monkeypatch.setattr(export_mod, "_load_page_from_envelope_file", lambda p: _make_page([word]))

    resp = client.get("/api/projects/test-project/export/styles")
    assert resp.status_code == 200
    assert resp.json() == []


def test_export_styles_route_symbol_exists(client: TestClient) -> None:
    """Sanity: the route handler symbol exists."""
    assert hasattr(export_api, "list_export_styles")
