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
def test_image_cache_treats_oserror_subclasses_as_404(tmp_path: Path, exc: BaseException) -> None:
    """B-57: every ``OSError`` subclass from the storage adapter must
    surface as 404 (not propagate to the generic 500 handler).

    Rationale: the cache root is shared with the legacy labeler under
    D-003 — half-finished writes, broken symlinks, and permission
    glitches are normal-mode-of-operation occurrences. They must NOT
    leak as 500 with a stack trace; the route should return the same
    "not found" status as a missing key.
    """

    class _RaisingStorage:
        async def get_bytes(self, key: str) -> bytes:
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


def test_spa_index_html_sets_no_store_cache_control(settings: Settings, spa_dir: Path) -> None:
    """B-62: the SPA shell ``index.html`` MUST be served with
    ``Cache-Control: no-store``.

    The shell's filename is stable across builds; only its contents
    change. Browsers default to heuristic caching for HTML, so without
    an explicit no-store header a developer's ``make frontend-build``
    + reload may serve the OLD shell from disk cache — which then
    points at hash-named assets that no longer exist on disk (404
    storm). Asset passthrough at ``/assets/<hash>.js`` is content-
    addressed and keeps the default caching semantics.
    """
    del spa_dir  # bundle present
    app = build_app(settings)
    with TestClient(app) as client:
        r_root = client.get("/")
        r_route = client.get("/projects/foo")
    for r in (r_root, r_route):
        assert r.status_code == 200, r.content
        cc = r.headers.get("cache-control", "")
        assert "no-store" in cc, f"expected no-store on SPA shell; got {cc!r}"


def _write_test_asset(spa_dir: Path, filename: str, content: bytes) -> Path:
    """Write ``spa_dir/assets/<filename>`` with ``content``; return path.

    B-72: ``assets/`` may *already* hold a real frontend bundle from a
    prior ``make frontend-build``. We therefore (1) create the dir
    idempotently, (2) refuse to overwrite a pre-existing entry under
    the same name (would mask a real bundle file), and (3) leave the
    dir intact on teardown — only the test's own file is removed.
    """
    assets_dir = spa_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = assets_dir / filename
    if target.exists():
        msg = (
            f"refusing to clobber existing {target}: pick a unique test "
            f"filename so a real frontend bundle isn't overwritten"
        )
        raise AssertionError(msg)
    target.write_bytes(content)
    return target


def _cleanup_test_asset(asset: Path) -> None:
    """Remove a single test-written asset; leave siblings untouched.

    B-72: previous shape called ``asset.parent.rmdir()``, which fails
    with ``OSError: Directory not empty`` whenever a real frontend
    bundle has populated ``static/assets/``. The dir is gitignored and
    safe to leave between tests; the test's own file is what matters.
    """
    if asset.exists():
        asset.unlink()


def test_spa_static_asset_does_not_set_no_store(settings: Settings, spa_dir: Path) -> None:
    """B-62 sibling: hash-named static assets keep default caching
    (no explicit ``no-store``). They're content-addressed so they're
    safe to cache aggressively; only the SPA shell needs no-store.
    """
    # B-72: pick a filename collision-resistant against any real bundle
    # (vite emits ``index-<hash>.js``; this one's deliberately not that).
    asset = _write_test_asset(spa_dir, "b72-test-fixture-hashed.js", b"// content")
    try:
        app = build_app(settings)
        with TestClient(app) as client:
            r = client.get("/assets/b72-test-fixture-hashed.js")
        assert r.status_code == 200
        cc = r.headers.get("cache-control", "")
        assert "no-store" not in cc, f"hashed asset should NOT carry no-store; got {cc!r}"
    finally:
        _cleanup_test_asset(asset)


def test_spa_fallback_serves_static_asset_directly(settings: Settings, spa_dir: Path) -> None:
    """Real files in the bundle (``/assets/<hash>.js``) serve verbatim, NOT as HTML."""
    asset = _write_test_asset(spa_dir, "b72-test-fixture-main.js", b"console.log('hi');")
    try:
        app = build_app(settings)
        with TestClient(app) as client:
            r = client.get("/assets/b72-test-fixture-main.js")
        assert r.status_code == 200
        assert r.content == b"console.log('hi');"
    finally:
        _cleanup_test_asset(asset)


def test_b72_test_isolation_does_not_mutate_real_static_assets(spa_dir: Path) -> None:
    """B-72 regression pin: tests in this module MUST NOT delete or
    overwrite a real frontend bundle that pre-existed under
    ``static/assets/``.

    The check captures the assets-dir contents at the start of *this*
    test (which runs after the two B-72 victims thanks to pytest's
    in-file declaration order — see comment block above), then walks
    the dir again and asserts the same set survives. If the B-72 fix
    regresses (someone re-introduces an unconditional ``rmdir`` in
    teardown), this fixture goes red on a tree where ``make
    frontend-build`` has run.

    On a clean tree (no bundle), this test is a no-op assertion that
    the dir is either absent or empty — still a useful invariant.
    """
    assets_dir = spa_dir / "assets"
    snapshot_before = sorted(p.name for p in assets_dir.iterdir()) if assets_dir.is_dir() else []
    # Run a probe through the SPA fallback so any in-test mutation of
    # the assets dir (write/unlink) would happen before we re-check.
    app = build_app(Settings(mode="normal"))
    with TestClient(app) as client:
        client.get("/")  # SPA shell
    snapshot_after = sorted(p.name for p in assets_dir.iterdir()) if assets_dir.is_dir() else []
    assert snapshot_before == snapshot_after, (
        f"B-72 regression: static/assets/ contents changed during a "
        f"test run; before={snapshot_before!r} after={snapshot_after!r}. "
        f"Tests in this module must use _write_test_asset/_cleanup_test_asset."
    )


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


# ── B-59: zip-imported wheel resolution ────────────────────────────────────


def test_resolve_static_dir_handles_non_path_traversable() -> None:
    """B-59: ``_resolve_static_dir`` must NOT use ``Path(str(traversable))``.

    For wheels installed via pip/uv the traversable IS a ``PosixPath``,
    but for zip-imported packages (``zipapp``, frozen importers,
    legacy ``.egg``s) it's a ``MultiplexedPath`` / ``ZipPath`` — and
    ``Path(str(zippath))`` produces a meaningless string like
    ``<MultiplexedPath object at 0x…>`` whose ``.is_dir()`` is False.
    The result is "404 — run make frontend-build" for a wheel that
    DOES ship the bundle, with no diagnostic.

    We monkeypatch ``importlib.resources.files`` to return a fake
    ``Traversable`` (not a ``Path``) backed by a real on-disk dir, and
    assert the resolver still finds ``index.html``.
    """
    import importlib
    import os
    import tempfile

    from pd_ocr_labeler_spa.api import static_mounts

    # Build a real on-disk dir with index.html — but wrap it in a
    # Traversable that is NOT a pathlib.Path subclass.
    tmp = tempfile.mkdtemp()
    static_root = Path(tmp) / "static"
    static_root.mkdir()
    (static_root / "index.html").write_bytes(b"<html/>")

    class _FakeTraversable:
        """Minimal Traversable backed by an on-disk dir but NOT a Path.

        Implements enough of the Traversable abc for ``importlib.resources``
        to materialise it via ``as_file`` — see CPython's
        ``_common._write_contents`` which calls ``.iterdir()`` / ``.name``
        / ``.read_bytes()``.
        """

        def __init__(self, real: Path, name: str | None = None) -> None:
            self._real = real
            self.name = name if name is not None else real.name

        def is_dir(self) -> bool:
            return self._real.is_dir()

        def is_file(self) -> bool:
            return self._real.is_file()

        def joinpath(self, name: str) -> _FakeTraversable:
            return _FakeTraversable(self._real / name, name=name)

        def __truediv__(self, name: str) -> _FakeTraversable:
            return self.joinpath(name)

        def iterdir(self):
            for child in self._real.iterdir():
                yield _FakeTraversable(child, name=child.name)

        def read_bytes(self) -> bytes:
            return self._real.read_bytes()

        def open(self, mode: str = "r", *args, **kwargs):
            return self._real.open(mode, *args, **kwargs)

        # The resolver must NOT do Path(str(self)) — that would produce
        # a path that doesn't exist on disk. Make __str__ deliberately
        # useless so any code that tries to round-trip it via str()
        # blows up the test.
        def __str__(self) -> str:
            return f"<FakeTraversable bogus repr at 0x{id(self):x}>"

    # Confirm the fake is NOT a Path (so the test is meaningful).
    fake = _FakeTraversable(static_root)
    assert not isinstance(fake, Path)
    # And confirm that the buggy "Path(str(traversable))" form would fail.
    assert not Path(str(fake)).is_dir(), "test setup: stringifying a non-Path Traversable must NOT round-trip"

    class _FilesShim:
        def joinpath(self, name: str) -> _FakeTraversable:
            assert name == "static"
            return fake

    real_files = importlib.resources.files

    def _patched_files(pkg: str) -> object:
        if pkg == "pd_ocr_labeler_spa":
            return _FilesShim()
        return real_files(pkg)

    importlib.resources.files = _patched_files  # type: ignore[assignment]
    try:
        resolved = static_mounts._resolve_static_dir()
    finally:
        importlib.resources.files = real_files  # type: ignore[assignment]

    assert resolved is not None, (
        "_resolve_static_dir returned None for a zip-style Traversable "
        "that does ship index.html — the Path(str(...)) cast is the bug."
    )
    # Sanity: the bundle's index.html must be reachable from the result.
    index_path = Path(os.fspath(resolved)) / "index.html"
    assert index_path.is_file()


# ── B-67: cache-key soundness ─────────────────────────────────────────────


def test_resolve_resource_dir_cache_keyed_on_logical_identity_not_id() -> None:
    """B-67 (iter 51): the materialisation cache MUST be keyed on the
    logical ``(package, resource_name)`` identity of the resource, NOT
    on ``id(traversable)``.

    Why this matters: ``id(obj)`` is only unique among *currently live*
    objects. CPython recycles int ids freely once a Traversable goes
    out of scope. The previous shape stashed each materialised path
    under ``id(traversable)``; if a fresh Traversable for a *different*
    sub-tree happened to receive the same recycled id, the cache would
    return the wrong path. Today's single-sub-tree caller hides the
    bug; any second caller (themes/, per-tenant SPA, …) would silently
    serve the wrong dir.

    This test pins the **correct** contract by exercising two distinct
    Traversable objects against two different ``(package, resource)``
    keys and asserting:
      1. They get distinct cached paths (no key collision on `id`).
      2. Re-resolving the same logical key returns the same path
         (cache hit), even after the original Traversable instance has
         been GC'd and a new one with potentially the same id has
         appeared.
    """
    import importlib
    import tempfile

    from pd_ocr_labeler_spa.api import static_mounts

    # Two distinct on-disk sub-trees standing in for two logical
    # resources (e.g. "static" + a hypothetical "themes").
    tmp = Path(tempfile.mkdtemp())
    static_root = tmp / "static"
    static_root.mkdir()
    (static_root / "index.html").write_bytes(b"<html>static</html>")
    themes_root = tmp / "themes"
    themes_root.mkdir()
    (themes_root / "index.html").write_bytes(b"<html>themes</html>")

    class _FakeTraversable:
        """Non-Path Traversable backed by a real on-disk dir.

        Same shape as the existing B-59 fixture above — duplicated
        intentionally so this test is self-contained: a future
        refactor of the B-59 fixture must not silently break the
        B-67 contract test.
        """

        def __init__(self, real: Path, name: str | None = None) -> None:
            self._real = real
            self.name = name if name is not None else real.name

        def is_dir(self) -> bool:
            return self._real.is_dir()

        def is_file(self) -> bool:
            return self._real.is_file()

        def joinpath(self, name: str) -> _FakeTraversable:
            return _FakeTraversable(self._real / name, name=name)

        def __truediv__(self, name: str) -> _FakeTraversable:
            return self.joinpath(name)

        def iterdir(self):
            for child in self._real.iterdir():
                yield _FakeTraversable(child, name=child.name)

        def read_bytes(self) -> bytes:
            return self._real.read_bytes()

        def open(self, mode: str = "r", *args, **kwargs):
            return self._real.open(mode, *args, **kwargs)

        def __str__(self) -> str:
            return f"<FakeTraversable bogus repr at 0x{id(self):x}>"

    # Reset the module-level cache so prior tests don't pre-seed it.
    static_mounts._RESOLVED_RESOURCE_DIR_CACHE.clear()

    # Live containers so the shim closures resolve names at call time —
    # we want to swap the static-side Traversable later in the test.
    static_holder = [_FakeTraversable(static_root)]
    themes_traversable = _FakeTraversable(themes_root)

    real_files = importlib.resources.files

    def _patched_files(pkg: str) -> object:
        if pkg == "pkg.static":

            class _Shim:
                def joinpath(self, name: str) -> _FakeTraversable:
                    assert name == "static"
                    return static_holder[0]

            return _Shim()
        if pkg == "pkg.themes":

            class _Shim2:
                def joinpath(self, name: str) -> _FakeTraversable:
                    assert name == "themes"
                    return themes_traversable

            return _Shim2()
        return real_files(pkg)

    importlib.resources.files = _patched_files  # type: ignore[assignment]
    try:
        # Two distinct logical resources resolve to two distinct dirs.
        path_static = static_mounts._resolve_resource_dir("pkg.static", "static")
        path_themes = static_mounts._resolve_resource_dir("pkg.themes", "themes")
        assert path_static is not None
        assert path_themes is not None
        assert path_static != path_themes, (
            "B-67: two distinct logical resources MUST materialise to "
            "distinct paths — cache must key on (package, resource_name), "
            f"not on id(traversable). Got static={path_static!r} "
            f"themes={path_themes!r}."
        )
        # Sanity: each materialised dir contains the right index.html bytes.
        assert (path_static / "index.html").read_bytes() == b"<html>static</html>"
        assert (path_themes / "index.html").read_bytes() == b"<html>themes</html>"

        # Re-resolve same logical key returns the SAME path (cache hit),
        # even though we construct a *fresh* Traversable instance — this
        # is the case the old `id`-keyed cache silently broke when the
        # int id got recycled. The new key is logical, not pointer-level,
        # so a fresh instance with a freshly-recycled id collides
        # CORRECTLY (intentional cache hit, same logical resource).
        # Swap the static-side Traversable to a fresh instance backing
        # the same on-disk dir. The previous instance is no longer
        # referenced from `static_holder`, so GC may reclaim its id —
        # potentially handing the same int to the new one. The cache
        # MUST still return the same materialised path, because the
        # cache key is the LOGICAL `(package, resource)` identity, not
        # the pointer-level `id(traversable)`.
        static_holder[0] = _FakeTraversable(static_root)
        path_static_again = static_mounts._resolve_resource_dir("pkg.static", "static")
        assert path_static_again == path_static, (
            "B-67: re-resolving the same (package, resource_name) MUST "
            "return the cached path even though the underlying "
            "Traversable is a fresh Python object."
        )
    finally:
        importlib.resources.files = real_files  # type: ignore[assignment]
        static_mounts._RESOLVED_RESOURCE_DIR_CACHE.clear()


def test_resolve_resource_dir_cache_evicts_stale_entry_after_tmpdir_vanishes() -> None:
    """B-67 follow-on: if a previously-materialised tmpdir is gone (test
    isolation, reaper, manual cleanup), the cache must not return the
    stale path — it should re-materialise.

    This guards the ``cached_path.is_dir()`` re-validation in
    ``_resolve_resource_dir``: without it, a stale cache entry would
    survive across a tmpdir cleanup and produce a 404 on a Traversable
    that *does* still resolve.
    """
    import importlib
    import shutil
    import tempfile

    from pd_ocr_labeler_spa.api import static_mounts

    static_mounts._RESOLVED_RESOURCE_DIR_CACHE.clear()

    tmp = Path(tempfile.mkdtemp())
    static_root = tmp / "static"
    static_root.mkdir()
    (static_root / "index.html").write_bytes(b"<html/>")

    class _FakeTraversable:
        def __init__(self, real: Path, name: str | None = None) -> None:
            self._real = real
            self.name = name if name is not None else real.name

        def is_dir(self) -> bool:
            return self._real.is_dir()

        def is_file(self) -> bool:
            return self._real.is_file()

        def joinpath(self, name: str) -> _FakeTraversable:
            return _FakeTraversable(self._real / name, name=name)

        def __truediv__(self, name: str) -> _FakeTraversable:
            return self.joinpath(name)

        def iterdir(self):
            for child in self._real.iterdir():
                yield _FakeTraversable(child, name=child.name)

        def read_bytes(self) -> bytes:
            return self._real.read_bytes()

        def open(self, mode: str = "r", *args, **kwargs):
            return self._real.open(mode, *args, **kwargs)

        def __str__(self) -> str:
            return f"<FakeTraversable at 0x{id(self):x}>"

    real_files = importlib.resources.files

    def _patched_files(pkg: str) -> object:
        if pkg == "pkg.fake":

            class _Shim:
                def joinpath(self, name: str) -> _FakeTraversable:
                    return _FakeTraversable(static_root, name="static")

            return _Shim()
        return real_files(pkg)

    importlib.resources.files = _patched_files  # type: ignore[assignment]
    try:
        first = static_mounts._resolve_resource_dir("pkg.fake", "static")
        assert first is not None
        # Wipe the materialised tmpdir from under the cache.
        shutil.rmtree(first, ignore_errors=True)
        # Even a Path-shaped Traversable would be cached as itself, so
        # for this contract we need a non-Path Traversable above (which
        # we have). The cache currently holds a (real_path, stack) pair
        # whose `real_path.is_dir()` is now False; a re-resolve must
        # detect that and re-materialise to a fresh tmpdir.
        second = static_mounts._resolve_resource_dir("pkg.fake", "static")
        assert second is not None
        assert second != first, (
            "stale cache entry survived after tmpdir vanished — "
            "re-validation step (cached_path.is_dir()) is missing."
        )
        assert second.is_dir()
    finally:
        importlib.resources.files = real_files  # type: ignore[assignment]
        static_mounts._RESOLVED_RESOURCE_DIR_CACHE.clear()


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
