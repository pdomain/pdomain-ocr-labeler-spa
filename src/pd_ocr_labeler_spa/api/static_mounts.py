"""Static-asset mounts: ``/image-cache/{key:path}`` + SPA catch-all.

Spec: ``specs/02-backend.md §2 step 12`` and ``§10`` (SPA / static
serving), plus ``§4`` (URL invariants — `/image-cache/{key:path}` is a
read-only StaticFiles-shaped mount served *through* the ``IStorage``
adapter, not directly off the filesystem; per D-019 the seam is the
adapter, not ``StaticFiles(directory=…)``).

Two functions, two mounts:

1. ``install_image_cache(app)`` — `GET /image-cache/{key:path}` reads
   bytes via ``app.state.storage.get_bytes(key)``. Path traversal is
   refused at the adapter layer (``FilesystemStorage._path`` raises
   ``ValueError`` on ``..``-escape or absolute-key tricks); we surface
   that as a 404 rather than 400, mirroring the "object not found"
   semantics every storage backend already uses for missing keys —
   the attacker can't distinguish "no such key" from "you can't have
   that key" by observing the status code.

2. ``install_spa_fallback(app)`` — `GET /{full_path:path}` serves the
   bundled SPA. Carve-outs: ``/api/*``, ``/healthz``, ``/env.js``,
   ``/docs``, ``/redoc``, ``/openapi.json``, ``/image-cache/*`` all 404
   normally rather than serve HTML — a 200 response with HTML for an
   unknown ``/api/...`` path would mask backend bugs and confuse the
   driver agent's pre-pass. The catch-all is registered LAST so it
   doesn't shadow real routes.

When the bundled SPA is missing (M0 dev mode — no ``make
frontend-build`` yet), the catch-all 404s with a helpful message
naming the missing dir and the build target. The `build_hooks/
spa_check.py` gate ensures production wheels can't ship in this state,
but local-dev iterations on the backend without a built SPA are
common and shouldn't crash with a `FileNotFoundError`.
"""

from __future__ import annotations

import logging
import os
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse

log = logging.getLogger(__name__)


# ── /image-cache/{key:path} ────────────────────────────────────────────────


# Reserved top-level prefixes the SPA fallback MUST NOT swallow. Every entry
# here is either a backend route (`/api/*`, `/healthz`, `/env.js`), a FastAPI-
# managed surface (`/docs`, `/redoc`, `/openapi.json`), or another mount
# (`/image-cache/*`). Adding a new top-level mount means adding it here too.
#
# Listed as a tuple of (literal, prefix-match) pairs:
# - ``literal=True`` matches the path EXACTLY.
# - ``literal=False`` matches the path OR any path prefixed with ``<value>/``.
_RESERVED_TOPLEVEL: tuple[tuple[str, bool], ...] = (
    ("api", False),
    ("healthz", True),
    ("env.js", True),
    ("docs", False),
    ("redoc", True),
    ("openapi.json", True),
    ("image-cache", False),
)


def install_image_cache(app: FastAPI) -> None:
    """Register `GET /image-cache/{key:path}` against ``app.state.storage``.

    Spec: ``specs/02-backend.md §10`` + D-019. Read-only over HTTP — the
    server is the only writer. The key is matched as a FastAPI ``path``
    converter so forward-slash-joined keys (``page-images/<project>/
    <hash>.png``) round-trip without URL-encoding the slashes.
    """

    @app.get("/image-cache/{key:path}", include_in_schema=False)
    async def _serve_image(key: str, request: Request) -> Response:
        # ``app.state.storage`` is the wired ``IStorage`` impl; we read it
        # off the request's app rather than via ``Depends(get_storage)``
        # so this route mounts cleanly even if the dependency-resolution
        # graph is being audited (it's a static-asset mount, not a
        # domain route).
        storage = request.app.state.storage

        try:
            data = await storage.get_bytes(key)
        except ValueError:
            # Path-traversal / absolute-key rejection from
            # FilesystemStorage._path. Surface as 404 — same status code
            # a missing key produces — so the rejection isn't an oracle
            # for "this key would have escaped if it existed".
            raise HTTPException(status_code=404, detail="not found") from None
        except OSError:
            # B-57: covers FileNotFoundError, IsADirectoryError,
            # PermissionError, broken-symlink OSError, etc. The cache
            # root is shared with the legacy labeler under D-003, so
            # mid-write / partial / permission-glitched files are a
            # normal-mode-of-operation possibility — they must surface
            # as a clean 404, not propagate to the generic 500 handler
            # (which would also leak the cache key into the response
            # body until B-51 lands). Logged at debug so operators with
            # a real disk problem still get a server-side breadcrumb.
            log.debug("Image cache read failed for key=%r", key, exc_info=True)
            raise HTTPException(status_code=404, detail="not found") from None

        # Cache-Control: served images are content-addressed (page hashes
        # under ``<cache>/page-images/``), so a long-lived cache is
        # safe — the SPA's image URLs change when the underlying bytes
        # change. ``immutable`` tells browsers not to revalidate within
        # the max-age window. Spec §10 doesn't pin specific values; we
        # default to 1h max-age which covers a working session without
        # being aggressive about long-term browser cache pressure.
        media_type = _guess_media_type(key)
        return Response(
            content=data,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=3600, immutable"},
        )


def _guess_media_type(key: str) -> str:
    """Map a storage key's extension to a Content-Type.

    Page images land as PNG or JPEG today; other extensions fall back to
    ``application/octet-stream`` rather than guessing. Adding a new
    image format means extending this map (one place).
    """
    ext = Path(key).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


# ── SPA fallback `/{full_path:path}` ───────────────────────────────────────


def _resolve_static_dir() -> Path | None:
    """Resolve the bundled SPA static dir, or ``None`` if it isn't present.

    Production: ``importlib.resources.files("pd_ocr_labeler_spa") /
    "static"`` resolves to the in-wheel directory. Dev: the same path
    against the source tree resolves to ``src/pd_ocr_labeler_spa/static/``,
    which is empty (just a ``.gitkeep``) until ``make frontend-build``
    has run.

    Returns ``None`` (rather than raising) when the dir is missing or
    empty, so the SPA fallback degrades gracefully in M0/dev mode.
    """
    try:
        traversable = resources.files("pd_ocr_labeler_spa").joinpath("static")
    except (FileNotFoundError, ModuleNotFoundError):
        return None

    path = Path(str(traversable))
    if not path.is_dir():
        return None
    if not (path / "index.html").is_file():
        # Empty static dir (M0 — only ``.gitkeep`` lives here). Not an
        # error: the catch-all just 404s with a helpful message instead
        # of trying to serve a non-existent ``index.html``.
        return None
    return path


def _is_reserved(full_path: str) -> bool:
    """Return ``True`` if ``full_path`` is owned by a non-SPA mount.

    The SPA fallback must not return HTML for ``/api/<anything>`` or any
    other backend-managed path; those should 404 normally so a real
    error isn't masked. ``full_path`` is the FastAPI path-converter
    capture — has no leading slash.
    """
    if not full_path:
        # Bare ``/`` is a SPA route (the React Router root).
        return False
    head = full_path.split("/", 1)[0]
    for prefix, literal in _RESERVED_TOPLEVEL:
        if literal:
            if full_path == prefix:
                return True
        else:
            if head == prefix:
                return True
    return False


def install_spa_fallback(app: FastAPI) -> None:
    """Register the SPA catch-all. MUST be called AFTER every other route.

    Spec: ``specs/02-backend.md §10``. Resolves ``frontend/dist`` (which
    is copied into ``src/pd_ocr_labeler_spa/static/`` by ``make
    frontend-build`` / the Dockerfile spa stage) and serves
    ``index.html`` for any non-reserved path. Static assets like
    ``/assets/<hash>.js`` are served directly from the dir (so the
    catch-all also doubles as the StaticFiles surface).

    Skipped when ``settings.frontend_dev_url`` is set — Vite runs
    separately on :5173, and the SPA is reached via that origin. The
    backend then only serves ``/api/*`` + ``/healthz`` + ``/env.js``.
    """
    settings = app.state.settings
    if settings.frontend_dev_url:
        log.info(
            "Frontend dev mode — visit %s for the SPA; FastAPI only serves /api/*",
            settings.frontend_dev_url,
        )
        return

    static_dir = _resolve_static_dir()
    if static_dir is None:
        log.warning(
            "SPA static bundle not found (expected `index.html` under "
            "src/pd_ocr_labeler_spa/static/). Run `make frontend-build` "
            "to populate it. The catch-all will 404 until then.",
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def _spa_fallback_missing(full_path: str) -> Response:
            if _is_reserved(full_path):
                raise HTTPException(status_code=404, detail="not found")
            raise HTTPException(
                status_code=404,
                detail=(
                    "SPA bundle not built — run `make frontend-build` "
                    "to populate src/pd_ocr_labeler_spa/static/."
                ),
            )

        return

    index_file = static_dir / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str) -> Response:
        if _is_reserved(full_path):
            raise HTTPException(status_code=404, detail="not found")
        # Direct file hit (e.g. ``/assets/<hash>.js``, ``/favicon.ico``):
        # serve the file. ``os.path.join`` then ``commonpath`` guards
        # against ``..``-escape via the path converter.
        if full_path:
            candidate = (static_dir / full_path).resolve()
            try:
                candidate.relative_to(static_dir.resolve())
            except ValueError:
                # ``..`` escape — refuse rather than serve.
                raise HTTPException(status_code=404, detail="not found") from None
            if candidate.is_file():
                return FileResponse(os.fspath(candidate))
        # Otherwise serve the SPA shell so the React Router can
        # take over for client-side routes like ``/projects/<id>``.
        # B-62: ``index.html`` has a stable filename across builds while
        # its contents change every build, and it points at hash-named
        # assets that disappear when a new build replaces them. Without
        # an explicit ``no-store`` browsers may serve a stale shell from
        # disk cache after ``make frontend-build`` (or a wheel upgrade)
        # and trigger a 404 storm against the old asset hashes. Hashed
        # assets above keep the default caching semantics — they're
        # content-addressed and safe to cache aggressively.
        return FileResponse(
            os.fspath(index_file),
            headers={"Cache-Control": "no-store"},
        )


__all__ = ["install_image_cache", "install_spa_fallback"]
