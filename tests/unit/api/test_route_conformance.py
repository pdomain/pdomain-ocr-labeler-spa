"""Route-level conformance: every JSON API route must declare response_model and status_code.

Acceptance criteria for issues #434 (F-029) and #435 (F-030):

#434 - Every ``@router.{get,post,...}`` route that is included in the OpenAPI
schema must declare an explicit ``response_model=``.  The acceptable values are:
    - A concrete Pydantic model (200/202 JSON routes).
    - ``response_model=None`` for routes with no response body (204) or for
      binary/SSE routes where ``response_class`` is explicitly set.

#435 - Routes that return a job-accepted shape (``{job_id}``) must declare
``status_code=202``.  Routes that return no body must declare ``status_code=204,
response_model=None``.  Routes that return a JSON payload synchronously must
declare ``status_code=200`` (or omit it, since 200 is the default).

Legitimate exceptions (excluded from the checks):
    - Routes with ``include_in_schema=False`` (image-cache, env.js, SPA catch-all).
    - SSE routes whose ``response_class`` is ``StreamingResponse`` — these
      intentionally cannot declare a Pydantic model (per CONVENTIONS.md).
    - Binary routes whose ``response_class`` is ``Response`` AND
      ``response_model=None`` is explicitly set — the ``None`` is the explicit
      declaration (per CONVENTIONS.md line 296-299).

CONVENTIONS.md reference: the ``FastAPI route handlers must declare an explicit
response_model`` rule (section at line 272).
"""

from __future__ import annotations

import pytest
from fastapi.datastructures import DefaultPlaceholder
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute


@pytest.fixture(scope="module")
def schema_routes() -> list[APIRoute]:
    """All APIRoute instances that are included in the OpenAPI schema."""
    from pd_ocr_labeler_spa.bootstrap import build_app

    app = build_app()
    return [r for r in app.routes if isinstance(r, APIRoute) and r.include_in_schema]


def test_every_schema_route_has_explicit_response_model(schema_routes: list[APIRoute]) -> None:
    """Every schema-included route must declare response_model= (even if None).

    ``response_model=None`` is the explicit FastAPI idiom for "no response body"
    (204 routes) or "binary/SSE route not expressible as Pydantic".  It is NOT
    the same as omitting ``response_model=`` entirely.

    FastAPI sets ``route.response_model`` to ``None`` when either:
    (a) the decorator explicitly passes ``response_model=None``, or
    (b) the decorator omits ``response_model=`` entirely — FastAPI cannot
        distinguish these two cases via the attribute alone.

    We distinguish them via the OpenAPI schema: if ``response_model=`` was
    omitted entirely, FastAPI will NOT include the route's success response in
    ``components/schemas``, and the ``responses/200/content`` will be absent or
    untyped.  For ``response_model=None`` (explicit 204), the OpenAPI ``responses``
    block will have no content entry.

    For this test we use a simpler, more robust signal: we check that every
    schema route with ``response_model is None`` also has an explicit
    ``status_code=204`` or an explicit non-default ``response_class`` (meaning
    the route author consciously opted out of JSON response modelling).
    """
    violations: list[str] = []
    for route in schema_routes:
        if route.response_model is not None:
            # Explicit model set — compliant.
            continue
        # response_model is None.  This is OK only if:
        #  (a) status_code == 204 (no-body), or
        #  (b) response_class is non-default (SSE / binary — explicit opt-out).
        sc = route.status_code
        rc = route.response_class
        rc_is_default = isinstance(rc, DefaultPlaceholder)

        if sc == 204:
            # Explicit 204 with response_model=None — correct per CONVENTIONS.
            continue
        if not rc_is_default:
            # SSE or binary with explicit response_class — accepted opt-out.
            # Require a comment in the decorator (can't test here) — the CONVENTIONS
            # rule says "document with an inline comment".  Trust the code author.
            continue
        # All other cases: response_model is absent and not justified.
        methods = ",".join(sorted(route.methods or []))
        violations.append(f"  {methods} {route.path}  (sc={sc})")

    assert not violations, (
        f"{len(violations)} route(s) lack an explicit response_model and are not "
        f"204/SSE/binary:\n" + "\n".join(violations) + "\n\nFix: add response_model=<Model> (JSON routes) or "
        "response_model=None + response_class=Response (binary) to the decorator."
    )


def test_202_routes_have_job_id_response_model(schema_routes: list[APIRoute]) -> None:
    """Every route with status_code=202 must have a response_model with a ``job_id`` field.

    Long-running routes enqueue a job and return immediately with
    ``{job_id: str}``.  Without a typed response_model the generated TypeScript
    degrades to ``unknown`` (F-029) and the status code advertises 200 (F-030).
    """
    violations: list[str] = []
    for route in schema_routes:
        if route.status_code != 202:
            continue
        rm = route.response_model
        if rm is None:
            methods = ",".join(sorted(route.methods or []))
            violations.append(f"  {methods} {route.path}  (response_model=None)")
            continue
        # Check the model has a job_id field.
        try:
            fields = rm.model_fields  # type: ignore[union-attr]
        except AttributeError:
            # Not a pydantic model; skip further inspection (unusual but possible
            # e.g. Generic aliases).
            continue
        if "job_id" not in fields:
            methods = ",".join(sorted(route.methods or []))
            violations.append(
                f"  {methods} {route.path}  "
                f"(response_model={rm.__name__ if hasattr(rm, '__name__') else rm!r} "
                f"has no job_id field)"
            )

    assert not violations, f"{len(violations)} 202-route(s) have an invalid response_model:\n" + "\n".join(
        violations
    )


def test_image_route_openapi_declares_jpeg(schema_routes: list[APIRoute]) -> None:
    """The page-image binary route must advertise image/jpeg in its OpenAPI 200 response.

    Acceptance criterion for F-031 (#436): before this fix the route omitted a
    ``responses=`` dict, so FastAPI fell back to ``content: {application/json: {}}``
    (the default for ``response_class=Response``).  The fix adds an explicit
    ``responses={200: {"content": {"image/jpeg": {}}}}`` to the decorator.

    We verify this by walking the live OpenAPI schema rather than inspecting the
    route object, so we catch any FastAPI serialisation quirk that could drop the
    override.
    """
    from pd_ocr_labeler_spa.bootstrap import build_app

    schema = build_app().openapi()
    # Locate the page-image path — ends with /{page_index}/image.
    image_paths = [p for p in schema.get("paths", {}) if p.endswith("/{page_index}/image")]
    assert image_paths, "Could not find /{page_index}/image path in OpenAPI schema"

    for path in image_paths:
        get_op = schema["paths"][path].get("get", {})
        responses = get_op.get("responses", {})
        content_200 = responses.get("200", {}).get("content", {})
        assert "image/jpeg" in content_200, (
            f"OpenAPI path {path} GET 200 content should include image/jpeg; "
            f"got: {list(content_200.keys())!r}"
        )
        # Also confirm JSON is NOT the sole advertised type (the bug was that
        # application/json:{} was the only entry).
        assert content_200 != {"application/json": {}}, (
            f"OpenAPI path {path} GET 200 content still shows the default "
            "application/json fallback — responses= override did not take effect"
        )


def test_sse_routes_use_streaming_response_class(schema_routes: list[APIRoute]) -> None:
    """SSE routes must set response_class=StreamingResponse and response_model=None.

    This ensures the conformance checker above can identify them as legitimate
    opt-outs without also requiring them to be excluded from the schema.
    """
    sse_paths = {
        "/api/jobs/{job_id}/events",
        "/api/notifications/stream",
    }
    for route in schema_routes:
        if route.path not in sse_paths:
            continue
        rc = route.response_class
        assert not isinstance(rc, DefaultPlaceholder), (
            f"SSE route {route.path} must set response_class=StreamingResponse explicitly"
        )
        assert issubclass(rc, StreamingResponse), (  # type: ignore[arg-type]
            f"SSE route {route.path} response_class must be StreamingResponse, got {rc!r}"
        )
        assert route.response_model is None, (
            f"SSE route {route.path} must set response_model=None (not omit it)"
        )
