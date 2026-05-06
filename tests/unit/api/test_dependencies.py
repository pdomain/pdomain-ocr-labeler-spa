"""``api.dependencies`` shape pins (spec ``02-backend.md §6``).

Each provider:

- Reads from ``request.app.state.<name>`` (we verify by hitting a tiny
  app that uses each provider as a route dependency).
- Returns the SAME identity for repeated calls (the providers don't
  re-build adapters per request — they surface the singleton wired at
  ``build_app(settings)`` time).
- Raises a wiring-clear ``RuntimeError`` if ``app.state.<name>`` is
  missing — the test boundary at which someone constructed a bare
  ``FastAPI()`` and forgot to call ``build_app(settings)``.

We deliberately don't mock the adapters — the spec ``§14`` testing
seam wires real (but hermetic) adapters. The unit-of-test here is the
*provider*, not the adapter, so a thin ``FastAPI`` app is the
fixture rather than a mock.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.adapters.auth import IAuth, NoneAuth
from pd_ocr_labeler_spa.adapters.ocr import IOCREngine, LocalDoctrOCR
from pd_ocr_labeler_spa.adapters.storage import FilesystemStorage, IStorage
from pd_ocr_labeler_spa.api.dependencies import (
    get_app_state,
    get_auth,
    get_ocr_engine,
    get_settings,
    get_storage,
)
from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.app_state import AppState
from pd_ocr_labeler_spa.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


def _attach_probe_routes(app: FastAPI) -> dict[str, list[int]]:
    """Attach probe routes that exercise each Depends provider.

    Returns a fresh ``ids`` dict that the routes append into via
    closure capture — one dict per fixture call (B-55: previously this
    was a module-global, which would have raced under ``pytest-xdist``
    and was a code smell besides — probe state belongs on the fixture,
    not the module).
    """
    ids: dict[str, list[int]] = {
        "settings": [],
        "app_state": [],
        "storage": [],
        "auth": [],
        "ocr_engine": [],
    }

    @app.get("/_probe/settings")
    def _settings_probe(s: Settings = Depends(get_settings)) -> dict[str, object]:
        ids["settings"].append(id(s))
        return {"type": type(s).__name__, "id": id(s)}

    @app.get("/_probe/app_state")
    def _app_state_probe(state: AppState = Depends(get_app_state)) -> dict[str, object]:
        ids["app_state"].append(id(state))
        return {"type": type(state).__name__, "id": id(state)}

    @app.get("/_probe/storage")
    def _storage_probe(storage: IStorage = Depends(get_storage)) -> dict[str, object]:
        ids["storage"].append(id(storage))
        return {"type": type(storage).__name__, "id": id(storage)}

    @app.get("/_probe/auth")
    def _auth_probe(auth: IAuth = Depends(get_auth)) -> dict[str, object]:
        ids["auth"].append(id(auth))
        return {"type": type(auth).__name__, "id": id(auth)}

    @app.get("/_probe/ocr")
    def _ocr_probe(ocr: IOCREngine = Depends(get_ocr_engine)) -> dict[str, object]:
        ids["ocr_engine"].append(id(ocr))
        return {"type": type(ocr).__name__, "id": id(ocr)}

    return ids


@pytest.fixture
def probe_state(settings: Settings) -> Iterator[tuple[TestClient, dict[str, list[int]]]]:
    """Yield a TestClient + the fresh per-fixture ``ids`` capture dict."""
    app = build_app(settings)
    ids = _attach_probe_routes(app)
    with TestClient(app) as c:
        yield c, ids


@pytest.fixture
def probed_client(
    probe_state: tuple[TestClient, dict[str, list[int]]],
) -> TestClient:
    """Back-compat alias for tests that don't need the ``ids`` dict."""
    return probe_state[0]


# ── per-provider type checks ───────────────────────────────────────────────


def test_get_settings_returns_settings_instance(probed_client: TestClient) -> None:
    r = probed_client.get("/_probe/settings")
    assert r.status_code == 200
    assert r.json()["type"] == "Settings"


def test_get_app_state_returns_app_state_instance(probed_client: TestClient) -> None:
    r = probed_client.get("/_probe/app_state")
    assert r.status_code == 200
    assert r.json()["type"] == "AppState"


def test_get_storage_returns_filesystem_storage(probed_client: TestClient) -> None:
    r = probed_client.get("/_probe/storage")
    assert r.status_code == 200
    assert r.json()["type"] == FilesystemStorage.__name__


def test_get_auth_returns_none_auth(probed_client: TestClient) -> None:
    r = probed_client.get("/_probe/auth")
    assert r.status_code == 200
    assert r.json()["type"] == NoneAuth.__name__


def test_get_ocr_engine_returns_local_doctr(probed_client: TestClient) -> None:
    r = probed_client.get("/_probe/ocr")
    assert r.status_code == 200
    assert r.json()["type"] == LocalDoctrOCR.__name__


# ── singleton identity stability across requests ──────────────────────────


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ("/_probe/settings", "settings"),
        ("/_probe/app_state", "app_state"),
        ("/_probe/storage", "storage"),
        ("/_probe/auth", "auth"),
        ("/_probe/ocr", "ocr_engine"),
    ],
)
def test_provider_returns_same_singleton_across_requests(
    probe_state: tuple[TestClient, dict[str, list[int]]],
    path: str,
    key: str,
) -> None:
    """Two GETs through the same provider must yield the SAME object id.

    If a provider accidentally re-built adapters per request the
    identity would drift; this pin closes that regression.
    """
    client, ids = probe_state
    r1 = client.get(path)
    r2 = client.get(path)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert ids[key] == [r1.json()["id"], r2.json()["id"]]
    assert r1.json()["id"] == r2.json()["id"]


def test_get_storage_yields_same_object_as_app_state_storage(
    probed_client: TestClient,
) -> None:
    """The flat ``app.state.storage`` and ``app.state.app_state.storage`` are the SAME object.

    ``bootstrap.build_app`` stashes both — the flat one for the
    spec §6 provider, the nested one as a sanity-check that AppState
    holds identity not a copy.
    """
    r1 = probed_client.get("/_probe/storage")
    r2 = probed_client.get("/_probe/app_state")
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Re-derive AppState's storage id by reaching into the running app
    # — TestClient.app is the FastAPI instance.
    app = probed_client.app
    assert id(app.state.storage) == id(app.state.app_state.storage)
    assert r1.json()["id"] == id(app.state.app_state.storage)


# ── failure mode: bare FastAPI() without bootstrap wiring ─────────────────


@pytest.mark.parametrize(
    ("provider", "missing_attr"),
    [
        (get_settings, "settings"),
        (get_app_state, "app_state"),
        (get_storage, "storage"),
        (get_auth, "auth"),
        (get_ocr_engine, "ocr_engine"),
    ],
)
def test_provider_raises_runtime_error_on_unwired_app(
    provider: object,
    missing_attr: str,
) -> None:
    """Every provider must raise a wiring-clear ``RuntimeError`` on a bare ``FastAPI()``.

    The spec §6 contract says: each provider points the test author at
    the missing ``app.state.<name>`` AND at ``bootstrap.build_app``.
    We pin all 5 here (B-52) — previously only ``get_storage`` was
    exercised, so a refactor that broke the wiring-error UX of any of
    the other 4 providers would slip through unit tests.

    The ``match=`` regex pins both halves of the message: the missing
    attribute name AND the ``bootstrap.build_app`` pointer — the
    *helpful* part, not just the exception class.
    """
    app = FastAPI()

    # Manually mount a route reading the unwired provider — exercise the
    # provider's failure path without going through ``build_app``.
    @app.get("/probe")
    def _probe(  # pragma: no cover - body unreached
        dep: object = Depends(provider),
    ) -> dict[str, str]:
        return {"ok": "yes"}

    with TestClient(app, raise_server_exceptions=True) as client:
        with pytest.raises(
            RuntimeError,
            match=rf"app\.state\.{missing_attr}.*bootstrap\.build_app",
        ):
            client.get("/probe")


# ── direct call shape (no FastAPI plumbing) ───────────────────────────────


def test_providers_callable_directly_with_request_like(settings: Settings) -> None:
    """The provider signature is ``(request: Request) -> X`` — no Depends chain.

    A direct call with a tiny request-like object whose ``.app.state``
    holds the wired bits succeeds. Pinning this shape makes the spec §6
    contract testable without ``TestClient`` for downstream code.
    """
    app = build_app(settings)

    class _Req:
        # FastAPI Request is heavy; the providers only touch ``.app.state``.
        # Quack-typing here is enough.
        def __init__(self, app: object) -> None:
            self.app = app

    req: Request = _Req(app)  # type: ignore[assignment]

    s = get_settings(req)
    state = get_app_state(req)
    storage = get_storage(req)
    auth = get_auth(req)
    ocr = get_ocr_engine(req)

    assert s is settings
    assert state is app.state.app_state
    assert storage is state.storage
    assert auth is state.auth
    assert ocr is state.ocr_engine
