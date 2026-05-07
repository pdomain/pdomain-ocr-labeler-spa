"""Static-asset mounts: ``/image-cache/{key:path}`` + SPA fallback.

Spec: ``specs/02-backend.md §2 step 12`` + ``§10`` + D-019.

The image-cache mount serves bytes via the wired ``IStorage`` adapter
(NOT directly through ``StaticFiles``); so we exercise it end-to-end
through ``TestClient`` against a real ``FilesystemStorage`` rooted at a
hermetic ``tmp_path``.

The SPA fallback serves ``index.html`` for any unknown route under
``/`` so the React Router can take over — but it MUST NOT swallow
``/api/*`` or other reserved prefixes; those must keep their normal
404 behaviour so backend bugs aren't masked. We pin both branches.

When the SPA bundle is missing (M0/dev mode — no ``make
frontend-build`` yet), the catch-all 404s with a helpful message
rather than crashing on a missing ``index.html``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """A hermetic ``Settings`` rooted under ``tmp_path``.

    ``mode="normal"`` so the SPA mount + image-cache are wired.
    ``cache_root`` lands under ``tmp_path`` so the FilesystemStorage's
    ``<cache>/page-images/`` root is writable & isolated.
    """
    return Settings(
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="normal",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def image_cache_root(settings: Settings) -> Path:
    """The on-disk root the FilesystemStorage adapter is rooted at.

    Per ``core.app_state._build_storage``, filesystem mode roots at
    ``<cache_root>/page-images/`` (matches spec §10's
    ``/image-cache/`` mount target). Tests put bytes here directly to
    simulate "OCR adapter populated this image".
    """
    root = settings.cache_root / "page-images"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ── /image-cache/{key:path} ────────────────────────────────────────────────


def test_image_cache_serves_existing_image(client: TestClient, image_cache_root: Path) -> None:
    """A real PNG under the image-cache root is served verbatim with image/png."""
    payload = b"\x89PNG\r\n\x1a\nfake-bytes-here"
    (image_cache_root / "alpha.png").write_bytes(payload)

    r = client.get("/image-cache/alpha.png")

    assert r.status_code == 200
    assert r.content == payload
    assert r.headers["content-type"] == "image/png"


def test_image_cache_404_on_missing_key(client: TestClient, image_cache_root: Path) -> None:
    """A key with no matching file 404s — same status the FilesystemStorage
    raises ``FileNotFoundError`` for under the hood."""
    del image_cache_root  # ensure dir exists; key intentionally absent
    r = client.get("/image-cache/nonexistent.png")
    assert r.status_code == 404


@pytest.mark.parametrize(
    "key",
    [
        "../etc/passwd",
        "../../etc/passwd",
        "subdir/../../escape.png",
    ],
)
def test_image_cache_blocks_path_traversal(client: TestClient, key: str) -> None:
    """``..``-escape attempts are refused with 404 (NOT 200).

    The 404 status matches "key not found" — an attacker can't
    distinguish "this key was rejected for traversal" from "this key
    just doesn't exist", so the rejection isn't an oracle. The
    rejection happens at ``FilesystemStorage._path`` (raises
    ``ValueError``), which the route surfaces as 404.
    """
    r = client.get(f"/image-cache/{key}")
    assert r.status_code == 404


def test_image_cache_serves_nested_keys(client: TestClient, image_cache_root: Path) -> None:
    """Forward-slash-joined keys (the storage-adapter convention) round-trip."""
    nested = image_cache_root / "project-foo" / "page0001.png"
    nested.parent.mkdir(parents=True, exist_ok=True)
    payload = b"nested-png-bytes"
    nested.write_bytes(payload)

    r = client.get("/image-cache/project-foo/page0001.png")

    assert r.status_code == 200
    assert r.content == payload


def test_image_cache_sets_immutable_cache_control(client: TestClient, image_cache_root: Path) -> None:
    """Page images are content-addressed; long-cache headers are safe."""
    (image_cache_root / "beta.png").write_bytes(b"x")
    r = client.get("/image-cache/beta.png")
    assert r.status_code == 200
    cc = r.headers.get("cache-control", "")
    assert "max-age" in cc
    assert "immutable" in cc


@pytest.mark.parametrize(
    "exc",
    [
        FileNotFoundError("missing"),
        IsADirectoryError("is dir"),
        PermissionError("denied"),
        OSError("broken symlink / ENOSPC"),
    ],
)
def test_image_cache_treats_oserror_subclasses_as_404(
    tmp_path: Path, exc: BaseException
) -> None:
    """B-57: every ``OSError`` subclass from the storage adapter must
    surface as 404 (not propagate to the generic 500 handler).

    Rationale: the cache root is shared with the legacy labeler under
    D-003 — half-finished writes, broken symlinks, and permission
    glitches are normal-mode-of-operation occurrences. They must NOT
    leak as 500 with a stack trace; the route should return the same
    "not found" status as a missing key.
    """

    class _RaisingStorage:
        async def get_bytes(self, key: str) -> bytes:  # noqa: ARG002
            raise exc

    s = Settings(
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="normal",
    )
    app = build_app(s)
    app.state.storage = _RaisingStorage()
    with TestClient(app) as client:
        r = client.get("/image-cache/whatever.png")
    assert r.status_code == 404, r.content


def test_image_cache_disabled_in_api_only_mode(tmp_path: Path) -> None:
    """``api_only`` mode skips the SPA bundle, /env.js, AND /image-cache."""
    s = Settings(
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )
    app = build_app(s)
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/image-cache/{key:path}" not in paths
    assert "/{full_path:path}" not in paths


# ── SPA fallback ──────────────────────────────────────────────────────────


def _populate_static_dir(content: bytes = b"<!doctype html><div id=root></div>") -> Path:
    """Write a stub ``index.html`` into the in-source ``static/`` dir.

    ``importlib.resources.files`` resolves to the source dir during
    pytest runs (the wheel isn't installed). We restore the original
    state in the fixture teardown so tests stay hermetic.
    """
    import pd_ocr_labeler_spa as pkg

    static_dir = Path(pkg.__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / "index.html").write_bytes(content)
    return static_dir


@pytest.fixture
def spa_dir() -> Iterator[Path]:
    """Populate the in-source SPA bundle for the test, then clean it up.

    The tests in this module need to flip between "bundle present" and
    "bundle absent" to exercise both branches of the SPA fallback.
    Tests that consume this fixture get a populated dir; tests that
    don't get the as-checked-in state (just ``.gitkeep``).
    """
    static_dir = _populate_static_dir()
    try:
        yield static_dir
    finally:
        index_file = static_dir / "index.html"
        if index_file.exists():
            index_file.unlink()


def test_spa_fallback_serves_index_for_unknown_route(settings: Settings, spa_dir: Path) -> None:
    """A non-API path under ``/`` returns the SPA shell (``index.html``)."""
    expected = (spa_dir / "index.html").read_bytes()

    app = build_app(settings)
    with TestClient(app) as client:
        r = client.get("/projects/some-project")

    assert r.status_code == 200
    assert r.content == expected
    assert "html" in r.headers.get("content-type", "")


def test_spa_fallback_serves_index_for_root(settings: Settings, spa_dir: Path) -> None:
    """Bare ``/`` returns the SPA shell (the React Router root)."""
    expected = (spa_dir / "index.html").read_bytes()
    app = build_app(settings)
    with TestClient(app) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert r.content == expected


def test_spa_fallback_serves_static_asset_directly(settings: Settings, spa_dir: Path) -> None:
    """Real files in the bundle (``/assets/<hash>.js``) serve verbatim, NOT as HTML."""
    asset = spa_dir / "assets" / "main.js"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"console.log('hi');")

    app = build_app(settings)
    try:
        with TestClient(app) as client:
            r = client.get("/assets/main.js")
        assert r.status_code == 200
        assert r.content == b"console.log('hi');"
    finally:
        asset.unlink()
        asset.parent.rmdir()


@pytest.mark.parametrize(
    "path",
    [
        "/api/nonexistent",
        "/api/projects/foo/pages/0",
        "/api/jobs",
    ],
)
def test_spa_fallback_does_not_swallow_api_routes(settings: Settings, spa_dir: Path, path: str) -> None:
    """Unknown ``/api/*`` paths 404 normally — they MUST NOT return HTML.

    A 200 HTML response for an unknown ``/api/...`` would mask backend
    bugs and confuse the driver agent's pre-pass.
    """
    del spa_dir  # bundle present; reserved-prefix carve-out is what we exercise
    app = build_app(settings)
    with TestClient(app) as client:
        r = client.get(path)
    assert r.status_code == 404
    # Body is JSON (FastAPI's standard 404), not HTML.
    assert "html" not in r.headers.get("content-type", "")


@pytest.mark.parametrize(
    "path",
    [
        "/healthz",  # real route — wins ahead of the catch-all
        "/env.js",  # real route — wins ahead of the catch-all
        "/image-cache/missing.png",  # real mount — 404s on missing key, not HTML
    ],
)
def test_spa_fallback_does_not_shadow_real_mounts(settings: Settings, spa_dir: Path, path: str) -> None:
    """``/healthz``, ``/env.js``, and ``/image-cache/*`` are real mounts.

    They must keep their own behaviour rather than being swallowed by
    the SPA catch-all. We exercise ``/healthz`` (200 JSON), ``/env.js``
    (200 javascript), and ``/image-cache/missing.png`` (404 — the
    image-cache mount handles it, NOT the catch-all).
    """
    del spa_dir
    app = build_app(settings)
    with TestClient(app) as client:
        r = client.get(path)
    # None of these paths return HTML; they hit the real mount.
    assert "html" not in r.headers.get("content-type", "")


def test_spa_fallback_404_when_dist_missing(settings: Settings) -> None:
    """When ``index.html`` is absent (M0/dev mode), the catch-all 404s.

    The error message names the missing dir + the build target so
    a developer iterating on the backend without a built SPA gets a
    pointer to the fix instead of an opaque ``FileNotFoundError``.
    """
    # Confirm the static dir is empty (just `.gitkeep`).
    import pd_ocr_labeler_spa as pkg

    static_dir = Path(pkg.__file__).parent / "static"
    assert not (static_dir / "index.html").exists(), (
        "test pre-condition: SPA bundle must be absent. "
        "Did `make frontend-build` run? Tear it down before this test."
    )

    app = build_app(settings)
    with TestClient(app) as client:
        r = client.get("/projects/foo")

    assert r.status_code == 404
    body = r.json()
    # ``api.middleware.error_handler`` wraps HTTPException as
    # ``{error, message, details}`` — read ``message``, not ``detail``.
    message = str(body.get("message", ""))
    assert "frontend-build" in message or "static" in message, body


def test_spa_fallback_skipped_when_frontend_dev_url_set(tmp_path: Path, spa_dir: Path) -> None:
    """``frontend_dev_url`` flips the SPA mount off — Vite serves the SPA.

    The backend then only handles ``/api/*`` + ``/healthz`` + ``/env.js``
    + ``/image-cache``. A bare ``/`` should NOT return the bundled
    index.html — it should 404 (FastAPI default for unmounted routes).
    """
    del spa_dir  # bundle present, but we expect the route NOT to mount
    s = Settings(
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="normal",
        frontend_dev_url="http://localhost:5173",
    )
    app = build_app(s)
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    # The catch-all is NOT registered.
    assert "/{full_path:path}" not in paths
    # /healthz, /env.js, /image-cache ARE still registered.
    assert "/healthz" in paths
    assert "/env.js" in paths
    assert "/image-cache/{key:path}" in paths


def test_spa_fallback_blocks_path_traversal_into_assets(settings: Settings, spa_dir: Path) -> None:
    """A traversal-shaped key in ``full_path`` doesn't leak files outside ``static/``.

    httpx normalises ``GET /../etc/passwd`` → ``GET /etc/passwd`` before
    it reaches the server, so the request that hits the route handler
    has ``full_path == "etc/passwd"`` — the catch-all should return the
    SPA shell, NOT the host's ``/etc/passwd``. We assert the response
    body is the bundled ``index.html`` (defence: the guard would only
    trigger on a non-normalised hop, but we still want to confirm a
    real traversal can't sneak through).
    """
    expected_index = (spa_dir / "index.html").read_bytes()
    app = build_app(settings)
    with TestClient(app) as client:
        r = client.get("/../etc/passwd")
    # Either way, never the host file.
    assert b"root:x:" not in r.content
    # And in the normalised case, it's the SPA shell.
    if r.status_code == 200:
        assert r.content == expected_index


# ── catch-all is registered LAST ──────────────────────────────────────────


def test_catch_all_registered_after_real_routes(settings: Settings) -> None:
    """The SPA fallback's path appears LAST in the route table.

    FastAPI matches routes in registration order, so the catch-all must
    be after every concrete route or it will shadow them.
    """
    app = build_app(settings)
    paths = [route.path for route in app.routes if hasattr(route, "path")]
    assert "/{full_path:path}" in paths
    assert paths[-1] == "/{full_path:path}", (
        "SPA catch-all must be the last registered route, otherwise it "
        "will shadow concrete mounts. Found order: " + ", ".join(paths)
    )
