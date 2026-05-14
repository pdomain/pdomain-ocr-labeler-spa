"""Static-asset mounts: ``/image-cache/{key:path}`` + SPA catch-all.

Spec: ``docs/architecture/02-backend.md §2 step 12`` and ``§10`` (SPA / static
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

    Spec: ``docs/architecture/02-backend.md §10`` + D-019. Read-only over HTTP — the
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

    Production (pip/uv-extracted wheel): ``importlib.resources.files(
    "pd_ocr_labeler_spa") / "static"`` returns a ``PosixPath`` we can
    use directly. Dev: the same path against the source tree resolves
    to ``src/pd_ocr_labeler_spa/static/``, also a ``Path``.

    Zip-imported packages (``zipapp``, frozen importer, legacy ``.egg``)
    return a non-``Path`` ``Traversable`` (e.g. ``MultiplexedPath`` /
    ``ZipPath``) — B-59. We check ``is_dir()`` and
    ``index.html`` existence on the Traversable directly (the abc
    defines both), then materialise to disk via ``resources.as_file``
    so the rest of the route handler (which expects a real on-disk
    ``Path``) sees the same shape regardless of import strategy.

    Returns ``None`` (rather than raising) when the dir is missing or
    empty, so the SPA fallback degrades gracefully in M0/dev mode.

    Materialisation results (for non-Path Traversables) are cached at
    *this* level keyed by ``(package_name, resource_name)`` — see
    :func:`_materialise_traversable` for the reasoning behind moving
    the cache up here (B-67).
    """
    return _resolve_resource_dir("pd_ocr_labeler_spa", "static")


# Module-level cache keyed by ``(package_name, resource_name)`` tuple. The
# cached *value* is a ``(materialised_path, ExitStack)`` pair: each cached
# entry owns exactly one ExitStack, so re-resolves are O(1) AND we don't
# leak orphaned tmpdirs on repeated calls (one stack per logical resource,
# not one stack per Traversable instance — B-67 lessons applied to B-71).
_RESOLVED_RESOURCE_DIR_CACHE: dict[tuple[str, str], tuple[Path, object]] = {}


def _resolve_resource_dir(package_name: str, resource_name: str) -> Path | None:
    """Resolve ``<package>/<resource>`` to an on-disk ``Path`` or ``None``.

    Factored out of :func:`_resolve_static_dir` so the caching contract
    (one entry per ``(package, resource)`` tuple) is testable against
    multiple sub-trees — the bug B-67 was about the inner helper using
    ``id(traversable)`` as a cache key, which is unsound under id-recycle
    once the Traversable goes out of scope.
    """
    cache_key = (package_name, resource_name)
    cached = _RESOLVED_RESOURCE_DIR_CACHE.get(cache_key)
    if cached is not None:
        cached_path, _stack = cached
        # Re-validate: a previously-materialised tmpdir could have been
        # cleaned up under our feet (test isolation, OS-level reaper);
        # in that case fall through and re-materialise. Cheap stat call.
        if cached_path.is_dir():
            return cached_path
        # Stale cache entry — drop it and recompute.
        _RESOLVED_RESOURCE_DIR_CACHE.pop(cache_key, None)

    try:
        traversable = resources.files(package_name).joinpath(resource_name)
    except (FileNotFoundError, ModuleNotFoundError):
        return None

    # Use the Traversable abc directly — works for both Path-backed
    # (pip-extracted) and non-Path-backed (zip-imported) traversables.
    # ``Path(str(traversable))`` would silently fail for the latter.
    try:
        if not traversable.is_dir():
            return None
        index = traversable.joinpath("index.html")
        if not index.is_file():
            # Empty static dir (M0 — only ``.gitkeep`` lives here).
            return None
    except (FileNotFoundError, NotADirectoryError):
        return None

    if isinstance(traversable, Path):
        # Fast path: pip/uv-extracted wheel or source tree — already a
        # real on-disk ``Path``, no materialisation needed. We do NOT
        # cache Path-shaped results: ``resources.files(...)`` is already
        # cheap and the lookup gives us the same Path on every call.
        return traversable

    # Zip-imported / frozen package: materialise to a tmpdir whose
    # lifetime spans the process. We hold the ExitStack reference in
    # the module-level cache value so the tmpdir survives.
    materialised = _materialise_traversable(traversable)
    if materialised is None:
        return None
    real_path, stack = materialised
    _RESOLVED_RESOURCE_DIR_CACHE[cache_key] = (real_path, stack)
    return real_path


def _materialise_traversable(traversable: object) -> tuple[Path, object] | None:
    """Extract a non-Path Traversable to disk and return ``(path, stack)``.

    Returns ``None`` if extraction fails or the result isn't a directory.
    The caller is responsible for retaining the returned ``ExitStack``
    so the underlying tmpdir survives — typically by stashing it in the
    process-wide :data:`_RESOLVED_RESOURCE_DIR_CACHE` keyed by
    ``(package, resource_name)``.

    B-67 (iter 51): the previous shape cached results inside this helper
    keyed by ``id(traversable)``. That key is unsound: once the
    Traversable goes out of scope, CPython is free to recycle its int
    id for an unrelated object, and the cache returns the wrong
    materialised Path. The correct cache key is the *logical* identity
    of the resource — its ``(package_name, resource_name)`` tuple —
    which is owned by the caller, not by us. So this helper no longer
    caches; the higher-level :func:`_resolve_resource_dir` does.
    """
    import contextlib

    stack = contextlib.ExitStack()
    try:
        materialised = stack.enter_context(resources.as_file(traversable))  # type: ignore[arg-type]
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        stack.close()
        return None

    real = Path(materialised)
    if not real.is_dir():
        stack.close()
        return None

    return real, stack


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

    Spec: ``docs/architecture/02-backend.md §10``. Resolves ``frontend/dist`` (which
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
