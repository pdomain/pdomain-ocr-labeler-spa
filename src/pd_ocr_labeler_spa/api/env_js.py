"""GET /env.js — runtime config shim for the SPA.

Per ``specs/02-backend.md §5.1``::

    GET /env.js → text/javascript
        window.__ENV__ = {API_BASE: "", API_TOKEN: null}

Cheap to regenerate; never cached. Loaded by ``index.html`` before the
React bundle so the SPA can read ``window.__ENV__`` synchronously.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from ..settings import Settings

router = APIRouter()


def _build_env(settings: Settings) -> dict[str, object]:
    # M0: auth is fixed at "none". The shape matches the spec's literal
    # example so the SPA bootstrap (M1) can rely on the contract.
    return {
        "API_BASE": "",
        "API_TOKEN": None,
    }


@router.get("/env.js", include_in_schema=False)
async def env_js(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    body = f"window.__ENV__ = {json.dumps(_build_env(settings))};\n"
    return Response(
        content=body,
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


def install_env_js(app) -> None:  # type: ignore[no-untyped-def]
    """Register ``/env.js``. Mount BEFORE the static SPA so the route wins."""
    app.include_router(router)
