"""Unit tests for ``GET /api/projects/{id}/pages/{idx}`` (spec-23-A, issue #306).

Spec authority:
- ``specs/23-page-payload-backend.md §3`` — target signature, payload
  assembly, error semantics, ``_build_image_url`` shape.

Slice contract:
- 200 response with populated ``PagePayload`` on valid index.
- ``image_url`` matches ``/api/projects/{id}/pages/{idx}/image?w={display_width}``.
- 404 ``project_not_found`` on missing project.
- 404 ``page_not_found`` on out-of-range page index.
- ``page_text_ocr`` / ``page_text_gt`` are strings (empty when no
  line_matches yet — pre-OCR initial GET).

The ``_page_payload`` helper is exported from ``api.pages`` so the
mutation endpoints in spec-23-C/D/E can reuse it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pdomain_ocr_labeler_spa.api.pages import (
    _build_image_url,
    _build_provenance_summary,  # GAP-1
    _page_payload,
    _render_plaintext,
)
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.models import EncodedDims
from pdomain_ocr_labeler_spa.settings import Settings

# Path to the tiny-fixture project shipped under tests/e2e/fixtures —
# 3 real 1x1 PNGs that PIL can open (size = (1, 1)).
TINY_FIXTURE = Path(__file__).resolve().parents[2] / "e2e" / "fixtures" / "projects" / "tiny-fixture"


def _make_settings(tmp_path: Path, source_projects_root: Path | None = None) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
        source_projects_root=source_projects_root,
    )


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    """Materialise a tiny-fixture-shaped project under tmp_path.

    Copies the shipped tiny-fixture PNGs (real 1x1 PNGs) into
    ``tmp_path/projects/tiny-fixture/`` so PIL can open them and
    ``EncodedDims.from_source_dims`` produces concrete dims.
    """
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "tiny-fixture"
    proj.mkdir()
    for src in sorted(TINY_FIXTURE.glob("*.png")):
        (proj / src.name).write_bytes(src.read_bytes())
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "tiny-fixture")},
        )
        assert resp.status_code == 200, resp.text
        yield c


@pytest.fixture
def bare_client(tmp_path: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


# ── _build_image_url ─────────────────────────────────────────────────


def test_build_image_url_shape() -> None:
    """``_build_image_url`` returns the spec-§3 image-route URL.

    Shape: ``/api/projects/{project_id}/pages/{page_index}/image?w={display_width}``.
    """
    dims = EncodedDims(src_width=2400, src_height=3200, display_width=1200, display_height=1600, scale=0.5)
    url = _build_image_url("book1", 0, dims)
    assert url == "/api/projects/book1/pages/0/image?w=1200"


def test_build_image_url_handles_none_dims() -> None:
    """When ``encoded_dims is None`` (image unreadable), ``_build_image_url``
    falls back to a URL without ``?w=`` so the frontend can still hit the
    route (the image-cache route is allowed to choose a default width)."""
    url = _build_image_url("book1", 0, None)
    assert url == "/api/projects/book1/pages/0/image"


# ── _render_plaintext ────────────────────────────────────────────────


def test_render_plaintext_empty_line_matches_returns_empty_string() -> None:
    """No line_matches → empty string (not None)."""
    assert _render_plaintext([], source="ocr", normalize_tabs=False) == ""
    assert _render_plaintext([], source="gt", normalize_tabs=False) == ""


# ── GET /pages/{idx} HTTP integration ────────────────────────────────


def test_get_page_returns_200_with_populated_payload(loaded_client: TestClient) -> None:
    """Valid page_index → 200 with a populated PagePayload.

    The tiny-fixture PNGs are 1x1; ``EncodedDims.from_source_dims`` ⇒
    ``display_width=1`` (under the 1200 cap). The payload's
    ``project_id`` / ``page_index`` echo the URL params; ``generation``
    is a non-negative int; plaintext strings are empty (no line_matches
    until OCR runs in a future slice).
    """
    resp = loaded_client.get("/api/projects/tiny-fixture/pages/0")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["project_id"] == "tiny-fixture"
    assert body["page_index"] == 0
    assert body["line_matches"] == []
    assert body["selection"]["selection_mode"] == "word"
    assert body["line_filter"] == "all"
    assert body["page_text_ocr"] == ""
    assert body["page_text_gt"] == ""
    assert isinstance(body["generation"], int)
    assert body["generation"] >= 0


def test_get_page_image_url_shape_matches_spec(loaded_client: TestClient) -> None:
    """``image_url`` matches ``/api/projects/{id}/pages/{idx}/image?w={display_width}``.

    For the 1x1 tiny-fixture, ``display_width=1``.
    """
    resp = loaded_client.get("/api/projects/tiny-fixture/pages/0")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["image_url"] == "/api/projects/tiny-fixture/pages/0/image?w=1"


def test_get_page_encoded_dims_from_source(loaded_client: TestClient) -> None:
    """``encoded_dims`` is populated from the on-disk image (PIL.Image.open).

    1x1 PNG → src_width=1, src_height=1, display_width=1, scale=1.0.
    """
    resp = loaded_client.get("/api/projects/tiny-fixture/pages/0")
    assert resp.status_code == 200, resp.text
    dims = resp.json()["encoded_dims"]

    assert dims is not None
    assert dims["src_width"] == 1
    assert dims["src_height"] == 1
    assert dims["display_width"] == 1
    assert dims["display_height"] == 1
    assert dims["scale"] == 1.0


def test_get_page_returns_404_when_no_project_loaded(bare_client: TestClient) -> None:
    """No project loaded → 404 ``project_not_found``."""
    resp = bare_client.get("/api/projects/book1/pages/0")
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_get_page_returns_404_when_project_id_mismatches(loaded_client: TestClient) -> None:
    """Wrong project_id → 404 ``project_not_found``."""
    resp = loaded_client.get("/api/projects/other_book/pages/0")
    assert resp.status_code == 404
    assert resp.json()["error"] == "project_not_found"


def test_get_page_returns_404_when_index_out_of_range(loaded_client: TestClient) -> None:
    """``page_index >= total_pages`` → 404 ``page_not_found``."""
    resp = loaded_client.get("/api/projects/tiny-fixture/pages/99")
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


def test_get_page_returns_404_for_negative_index(loaded_client: TestClient) -> None:
    """Negative ``page_index`` → 404 (FastAPI int-coercion accepts ``-1``)."""
    resp = loaded_client.get("/api/projects/tiny-fixture/pages/-1")
    assert resp.status_code == 404
    assert resp.json()["error"] == "page_not_found"


# ── _page_payload helper reuse ───────────────────────────────────────


def test_page_payload_helper_is_exported() -> None:
    """``_page_payload`` is importable from ``api.pages`` so mutation
    endpoints in spec-23-C/D/E can reuse it.

    Per the spec keystone contract: the helper signature is module-level
    (not endpoint-bound) so a mutation handler can apply a state change
    then call ``_page_payload(project_id, page_index, project_state, settings)``
    to refresh the response payload.
    """
    from pdomain_ocr_labeler_spa.api import pages as pages_module

    assert callable(pages_module._page_payload)


def test_page_payload_helper_returns_payload_for_loaded_project(
    loaded_client: TestClient,
) -> None:
    """Direct ``_page_payload`` call on the in-process state returns the
    same shape the HTTP route would.

    This guards the helper-vs-route parity contract: future mutation
    endpoints will call ``_page_payload`` directly, and the shape MUST
    match what GET produces.
    """
    app = loaded_client.app  # pyright: ignore[reportAttributeAccessIssue, reportFunctionMemberAccess]
    project_state = app.state.project_state  # pyright: ignore[reportAttributeAccessIssue, reportFunctionMemberAccess]
    settings = app.state.settings  # pyright: ignore[reportAttributeAccessIssue, reportFunctionMemberAccess]

    payload = _page_payload(
        project_id="tiny-fixture",
        page_index=0,
        project_state=project_state,
        settings=settings,
    )

    assert payload.project_id == "tiny-fixture"
    assert payload.page_index == 0
    assert payload.image_url == "/api/projects/tiny-fixture/pages/0/image?w=1"
    assert payload.encoded_dims is not None
    assert payload.encoded_dims.src_width == 1


# ── _build_provenance_summary (GAP-1) ────────────────────────────────
#
# The local _build_provenance_summary in api/pages.py is a stub that
# always returns None (GAP-1 deferred). The rich provenance rendering
# is now ops.build_provenance_summary(ProvenanceGraph).
#
# Tests below:
# 1. Verify the local stub always returns None (no regressions on the stub).
# 2. Test ops.build_provenance_summary directly with ProvenanceGraph inputs —
#    this is the canonical successor to the old saved_provenance / ocr_provenance
#    fields that were on the legacy PageRecord.


def test_build_provenance_summary_stub_always_returns_none() -> None:
    """The local _build_provenance_summary stub in api/pages.py returns None.

    This is intentional (GAP-1 deferred). The ops provenance summary is tested
    separately below. Successor to the 7 retired saved_provenance tests.
    """
    assert _build_provenance_summary(None) is None
    assert _build_provenance_summary("anything") is None  # type: ignore[arg-type]
    assert _build_provenance_summary({"ocr": {"engine": "doctr"}}) is None  # type: ignore[arg-type]


# ── ops.build_provenance_summary — new-contract coverage ─────────────────────
#
# These tests exercise the ops function that _assemble_page_payload calls.
# They replace the 7 skip-marked tests that used legacy saved_provenance fields.


def _make_prov_graph(nodes: dict, head_id: str = "", history: list | None = None):
    """Build a minimal ProvenanceGraph for tests."""
    from pdomain_ops.pages import ProvenanceGraph, ProvenanceNode

    built_nodes = {}
    for nid, nd in nodes.items():
        built_nodes[nid] = ProvenanceNode(
            id=nid,
            source=nd.get("source", "test"),
            tool=nd.get("tool"),
        )
    return ProvenanceGraph(
        nodes=built_nodes,
        head_id=head_id or (next(iter(built_nodes)) if built_nodes else ""),
        history=history or [],
    )


def test_ops_provenance_summary_none_graph_returns_sentinel() -> None:
    """ops.build_provenance_summary(None) returns the 'no provenance' sentinel."""
    from pdomain_ops.pages import build_provenance_summary as ops_build

    assert ops_build(None) == "no provenance"


def test_ops_provenance_summary_single_node_no_tool() -> None:
    """A single OCR node with no tool shows just the source."""
    from pdomain_ops.pages import build_provenance_summary as ops_build

    graph = _make_prov_graph({"ocr-1": {"source": "ocr"}}, head_id="ocr-1")
    summary = ops_build(graph)
    assert "ocr" in summary
    assert "no provenance" not in summary


def test_ops_provenance_summary_single_node_with_tool() -> None:
    """A node with source + tool shows 'source(tool)'."""
    from pdomain_ops.pages import build_provenance_summary as ops_build

    graph = _make_prov_graph({"n1": {"source": "ocr", "tool": "doctr"}}, head_id="n1")
    assert "ocr(doctr)" in ops_build(graph)


def test_ops_provenance_summary_chain_via_history() -> None:
    """History list is walked in order: node1 → node2."""
    from pdomain_ops.pages import build_provenance_summary as ops_build

    graph = _make_prov_graph(
        {"n1": {"source": "ingest"}, "n2": {"source": "labeler"}},
        head_id="n2",
        history=["n1", "n2"],
    )
    result = ops_build(graph)
    assert "ingest" in result
    assert "labeler" in result
    # History order preserved
    assert result.index("ingest") < result.index("labeler")


def test_ops_provenance_summary_empty_nodes_returns_sentinel() -> None:
    """Empty node dict → 'no provenance'."""
    from pdomain_ops.pages import ProvenanceGraph
    from pdomain_ops.pages import build_provenance_summary as ops_build

    empty = ProvenanceGraph()
    assert ops_build(empty) == "no provenance"


def test_ops_provenance_summary_head_fallback_when_no_history() -> None:
    """When history is empty, falls back to head_id node."""
    from pdomain_ops.pages import build_provenance_summary as ops_build

    graph = _make_prov_graph(
        {"h1": {"source": "ocr", "tool": "doctr"}},
        head_id="h1",
        history=[],
    )
    result = ops_build(graph)
    assert "ocr(doctr)" in result
