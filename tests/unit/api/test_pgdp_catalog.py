from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from pydantic import JsonValue

from pdomain_ocr_labeler_spa.adapters.source_data import SourceDataBridge
from pdomain_ocr_labeler_spa.api.pgdp import ProjectCatalog, projects

if TYPE_CHECKING:
    import pytest


async def test_default_catalog_preserves_bounded_sparse_result_without_empty_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SourceDataBridge(python=None, corpus_root=None, output_root=None)
    requests: list[Mapping[str, object]] = []

    async def call(request: Mapping[str, object], **_kwargs: object) -> dict[str, JsonValue]:
        requests.append(request)
        return {
            "projects": [],
            "offset": 0,
            "limit": 25,
            "next_offset": 25,
            "scanned_count": 25,
            "truncated": True,
            "warnings": [],
        }

    monkeypatch.setattr(bridge, "call", call)
    result = await projects(bridge=bridge, query="", limit=25, offset=0)
    assert isinstance(result, ProjectCatalog)
    assert result.truncated and result.next_offset == 25
    assert "query" not in requests[0]
