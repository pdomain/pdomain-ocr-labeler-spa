"""Verify all spec-listed wire shapes appear in the OpenAPI schema.

Acceptance criteria for issue #182:
- ``make openapi-export`` generates ``frontend/src/api/types.ts`` with no error
- ``tsc --noEmit`` passes on the generated types
- No route handler references an undeclared model shape

These checks are proxied by verifying that ``build_app().openapi()`` includes
every shape from spec §Decision/Wire shapes and that the app builds without
raising (which proves no route references an undeclared model).
"""

from __future__ import annotations


def test_openapi_schema_contains_all_spec_wire_shapes() -> None:
    """All spec-listed wire shapes must appear in components.schemas of the OpenAPI output."""
    from pdomain_ocr_labeler_spa.bootstrap import build_app

    app = build_app()
    schema = app.openapi()
    schemas = schema.get("components", {}).get("schemas", {})

    required = [
        # Domain models that surface through route usage
        "BBox",
        "MatchStatus",
        "LineFilter",
        "PageRecord",
        "EncodedDims",
        "WordMatch",
        "LineMatch",
        # Page shapes
        "PagePayload",
        "SavePageRequest",
        "SavePageResponse",
        "SaveProjectResponse",
        "SaveFailure",
        "ReloadOCRRequest",
        "RematchGtRequest",
        # Project shapes
        "SetSourceProjectsRootRequest",
        "SetSourceProjectsRootResponse",
        # Word shapes
        "UpdateWordGroundTruthRequest",
        "ApplyStyleRequest",
        "ApplyComponentRequest",
        "ToggleValidatedRequest",
        "ValidateBatchRequest",
        "AddWordRequest",
        "ReboxWordRequest",
        "NudgeBboxRequest",
        "SplitWordRequest",
        "MergeWordsRequest",
        "ErasePixelsRequest",
        # Line/paragraph shapes
        "CopyLineGtRequest",
        "DeleteScopeRequest",
        "MergeScopeRequest",
        "SplitParagraphAfterLineRequest",
        "SplitLineAfterWordRequest",
        "SplitLineWithSelectedWordsRequest",
        "GroupSelectedWordsIntoNewParagraphRequest",
        # Refine
        "RefineScopeRequest",
        # Export
        "ExportScope",
        "ExportRequest",
        "ExportResponse",
        # Jobs
        "JobStatus",
        "JobType",
        "JobProgress",
        "Job",
    ]

    missing = [s for s in required if s not in schemas]
    assert not missing, f"OpenAPI schema missing {len(missing)} wire shapes: {missing}"


def test_no_route_handler_references_undeclared_model() -> None:
    """build_app() must succeed — any route with an undeclared response_model raises at build time."""
    from pdomain_ocr_labeler_spa.bootstrap import build_app

    app = build_app()
    # If this raises, a route references an undefined model.
    schema = app.openapi()
    assert "paths" in schema
    assert "components" in schema
