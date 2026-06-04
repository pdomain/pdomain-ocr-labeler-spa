"""Q-B2-STYLE-LABELS option (b): GET /api/label-vocabulary acceptance tests.

The endpoint MUST return exactly the sets imported from
``pdomain_book_tools.ocr.label_normalization``, so the frontend always
sees the canonical vocabulary and can never drift.

Spec authority: OPEN_QUESTIONS.md Q-B2-STYLE-LABELS (resolved by this slice).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pdomain_book_tools.ocr.label_normalization import (
    ALLOWED_COMPONENTS,
    ALLOWED_TEXT_STYLE_LABELS,
)

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    return TestClient(app)


class TestLabelVocabularyRoute:
    """GET /api/label-vocabulary returns the canonical book-tools vocab."""

    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/label-vocabulary")
        assert resp.status_code == 200

    def test_content_type_json(self, client: TestClient) -> None:
        resp = client.get("/api/label-vocabulary")
        assert "application/json" in resp.headers["content-type"]

    def test_text_style_labels_match_book_tools_exactly(self, client: TestClient) -> None:
        """The returned text_style_labels must equal ALLOWED_TEXT_STYLE_LABELS."""
        resp = client.get("/api/label-vocabulary")
        data = resp.json()
        assert set(data["text_style_labels"]) == ALLOWED_TEXT_STYLE_LABELS

    def test_word_components_match_book_tools_exactly(self, client: TestClient) -> None:
        """The returned word_components must equal ALLOWED_COMPONENTS."""
        resp = client.get("/api/label-vocabulary")
        data = resp.json()
        assert set(data["word_components"]) == ALLOWED_COMPONENTS

    def test_text_style_labels_are_sorted(self, client: TestClient) -> None:
        """Labels must be sorted (canonical, deterministic order)."""
        resp = client.get("/api/label-vocabulary")
        data = resp.json()
        labels = data["text_style_labels"]
        assert labels == sorted(labels)

    def test_word_components_are_sorted(self, client: TestClient) -> None:
        """Components must be sorted (canonical, deterministic order)."""
        resp = client.get("/api/label-vocabulary")
        data = resp.json()
        comps = data["word_components"]
        assert comps == sorted(comps)

    def test_superscript_and_subscript_are_in_components_not_styles(self, client: TestClient) -> None:
        """superscript and subscript are COMPONENTS, NOT text styles."""
        resp = client.get("/api/label-vocabulary")
        data = resp.json()
        style_set = set(data["text_style_labels"])
        comp_set = set(data["word_components"])
        # Must be in components
        assert "superscript" in comp_set
        assert "subscript" in comp_set
        # Must NOT be in styles
        assert "superscript" not in style_set
        assert "subscript" not in style_set

    def test_no_unknown_style_labels(self, client: TestClient) -> None:
        """No label in text_style_labels is outside book-tools' ALLOWED set."""
        resp = client.get("/api/label-vocabulary")
        data = resp.json()
        unknown = set(data["text_style_labels"]) - ALLOWED_TEXT_STYLE_LABELS
        assert unknown == set(), f"Unknown style labels returned: {unknown}"

    def test_no_unknown_component_labels(self, client: TestClient) -> None:
        """No label in word_components is outside book-tools' ALLOWED set."""
        resp = client.get("/api/label-vocabulary")
        data = resp.json()
        unknown = set(data["word_components"]) - ALLOWED_COMPONENTS
        assert unknown == set(), f"Unknown component labels returned: {unknown}"

    def test_response_shape_has_both_fields(self, client: TestClient) -> None:
        """Response body has exactly text_style_labels and word_components keys."""
        resp = client.get("/api/label-vocabulary")
        data = resp.json()
        assert "text_style_labels" in data
        assert "word_components" in data
