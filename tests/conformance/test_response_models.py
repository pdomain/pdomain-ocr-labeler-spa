"""Conformance test: every JSON API route must declare an explicit response_model.

Spec authority:
- ``CONVENTIONS.md §Rule: FastAPI route handlers must declare an explicit
  response_model`` (line 272+).
- Issue #434 [F-029] — cited routes lacked ``response_model``; this test guards
  the contract going forward.

What this checks
----------------
For every ``@router.{get,post,put,patch,delete}`` route mounted under ``/api``:

1. Non-SSE, non-binary routes must have a typed schema in the OpenAPI
   ``responses["200"]`` (or the route's declared status code).  A missing
   ``response_model`` causes FastAPI to emit ``{}`` in the schema, which
   is how we detect the violation.
2. SSE routes (``text/event-stream``) are explicitly excluded — FastAPI
   cannot express a streaming body as a Pydantic model.
3. Binary / image routes (``image/*``) are explicitly excluded — same
   reason; they carry raw bytes not JSON.
4. Routes that return no body (``204 No Content``) are expected to have
   ``response_model=None`` (no schema in ``responses["204"]``).

The test operates on the app's OpenAPI schema rather than inspecting
FastAPI's internal route objects, so it works identically in production
and in CI with a minimal ``build_app`` call.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _build_test_settings(tmp_path_factory) -> Settings:  # type: ignore[no-untyped-def]
    tmp = tmp_path_factory.mktemp("openapi_conformance")
    return Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp / "config",
        data_root=tmp / "data",
        cache_root=tmp / "cache",
        mode="api_only",
    )


def _schema_has_typed_content(response_entry: dict) -> bool:  # type: ignore[type-arg]
    """Return True if a responses entry has typed JSON content (not empty schema)."""
    content = response_entry.get("content", {})
    if not content:
        # No content at all — acceptable for 204 No Content only.
        return False
    for media_type, media_info in content.items():
        if media_type.startswith("image/") or media_type == "text/event-stream":
            # Binary / SSE — not a JSON route, skip.
            return True  # "OK" — don't flag as violation
        if media_type == "application/json":
            schema = media_info.get("schema", {})
            # FastAPI emits {} or {"type": "null"} for response_model=None (204)
            # or an untyped dict when response_model is absent.
            # A typed route will have at least a "$ref", "properties", "type", or "allOf".
            has_type = bool(
                schema.get("$ref")
                or schema.get("properties")
                or schema.get("allOf")
                or schema.get("anyOf")
                or schema.get("items")
                # list[str] renders as {"type": "array", "items": {...}}
                or (schema.get("type") == "array" and schema.get("items"))
            )
            return has_type
    return False


def _is_sse_or_binary_route(path_item_op: dict) -> bool:  # type: ignore[type-arg]
    """Return True if the operation's 200 response is SSE or binary (image)."""
    responses = path_item_op.get("responses", {})
    for resp in responses.values():
        content = resp.get("content", {})
        for media_type in content:
            if media_type.startswith("image/") or media_type == "text/event-stream":
                return True
    return False


# Intentional exceptions: routes that cannot express a Pydantic response_model.
# Each entry is (method, path) exactly as it appears in the OpenAPI schema.
# Documented exceptions:
#   - SSE routes: FastAPI cannot express a streaming body as a Pydantic model.
#     The inline decorator comment explains the exemption per CONVENTIONS.md.
#   - Binary image routes: return raw JPEG bytes via Response/FileResponse.
_INTENTIONAL_EXCEPTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        # SSE stream — spec §5.10; intentional exception per CONVENTIONS.md §judgment-call
        ("get", "/api/jobs/{job_id}/events"),
        # SSE stream — spec §5.11; intentional exception per CONVENTIONS.md §judgment-call
        ("get", "/api/notifications/stream"),
        # Binary image — returns raw JPEG bytes, not JSON; response_model not applicable
        ("get", "/api/projects/{project_id}/pages/{page_index}/image"),
    }
)


def test_all_json_routes_have_typed_response_model(tmp_path_factory) -> None:  # type: ignore[no-untyped-def]
    """Every /api JSON route must advertise a typed response schema in OpenAPI.

    This guards CONVENTIONS.md §Rule: FastAPI route handlers must declare an
    explicit response_model.  Issue #434 [F-029].

    Failure message names the violating path + method so the developer can
    immediately locate the route.
    """
    settings = _build_test_settings(tmp_path_factory)
    app = build_app(settings)

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    violations: list[str] = []

    paths = schema.get("paths", {})
    for path, path_item in paths.items():
        if not path.startswith("/api"):
            # Skip non-API routes (SPA catch-all, /healthz already typed)
            continue

        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if operation is None:
                continue

            if _is_sse_or_binary_route(operation):
                # Auto-detected SSE or binary — cannot be expressed as Pydantic model
                continue

            if (method, path) in _INTENTIONAL_EXCEPTIONS:
                # Explicitly documented exception — SSE stream or binary route
                continue

            responses = operation.get("responses", {})

            # Find the primary success response (200, 201, 202, 204)
            success_codes = [code for code in responses if code.startswith("2")]
            if not success_codes:
                continue  # unusual but not our concern here

            # 204 No Content is fine — it has no body by definition
            if success_codes == ["204"]:
                continue

            for code in success_codes:
                if code == "204":
                    continue
                resp_entry = responses[code]
                if not _schema_has_typed_content(resp_entry):
                    violations.append(
                        f"  {method.upper()} {path} → HTTP {code}: "
                        "response has no typed JSON schema (add response_model=<Model>)"
                    )

    assert not violations, (
        "The following /api routes are missing a typed response_model.\n"
        "Fix each by adding `response_model=<SomePydanticModel>` to the "
        "@router decorator.\n"
        "See CONVENTIONS.md §Rule: FastAPI route handlers must declare an "
        "explicit response_model.\n\n" + "\n".join(violations)
    )
