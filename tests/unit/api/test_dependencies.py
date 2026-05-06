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


# Track each provider's returned object across requests so we can assert
# identity-stability of the singleton. ``id()`` is sufficient — no
# attempt to JSON-serialise the adapter object goes over the wire.
_LAST_IDS: dict[str, list[int]] = {
    "settings": [],
    "app_state": [],
    "storage": [],
    "auth": [],
    "ocr_engine": [],
}


def _attach_probe_routes(app: FastAPI) -> None:
    """Attach probe routes that exercise each Depends provider."""
    _LAST_IDS["settings"].clear()
    _LAST_IDS["app_state"].clear()
    _LAST_IDS["storage"].clear()
    _LAST_IDS["auth"].clear()
    _LAST_IDS["ocr_engine"].clear()

    @app.get("/_probe/settings")
    def _settings_probe(s: Settings = Depends(get_settings)) -> dict[str, object]:
        _LAST_IDS["settings"].append(id(s))
        return {"type": type(s).__name__, "id": id(s)}

    @app.get("/_probe/app_state")
    def _app_state_probe(state: AppState = Depends(get_app_state)) -> dict[str, object]:
        _LAST_IDS["app_state"].append(id(state))
        return {"type": type(state).__name__, "id": id(state)}

    @app.get("/_probe/storage")
    def _storage_probe(storage: IStorage = Depends(get_storage)) -> dict[str, object]:
        _LAST_IDS["storage"].append(id(storage))
        return {"type": type(storage).__name__, "id": id(storage)}

    @app.get("/_probe/auth")
    def _auth_probe(auth: IAuth = Depends(get_auth)) -> dict[str, object]:
        _LAST_IDS["auth"].append(id(auth))
        return {"type": type(auth).__name__, "id": id(auth)}

    @app.get("/_probe/ocr")
    def _ocr_probe(ocr: IOCREngine = Depends(get_ocr_engine)) -> dict[str, object]:
        _LAST_IDS["ocr_engine"].append(id(ocr))
        return {"type": type(ocr).__name__, "id": id(ocr)}


@pytest.fixture
def probed_client(settings: Settings) -> Iterator[TestClient]:
    app = build_app(settings)
    _attach_probe_routes(app)
    with TestClient(app) as c:
        yield c


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
    probed_client: TestClient,
    path: str,
    key: str,
) -> None:
    """Two GETs through the same provider must yield the SAME object id.

    If a provider accidentally re-built adapters per request the
    identity would drift; this pin closes that regression.
    """
    r1 = probed_client.get(path)
    r2 = probed_client.get(path)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert _LAST_IDS[key] == [r1.json()["id"], r2.json()["id"]]
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


def test_get_storage_raises_runtime_error_on_unwired_app() -> None:
    """A test that builds ``FastAPI()`` directly (no ``build_app``) hits a clear error."""
    app = FastAPI()
    # Manually mount a route reading the unwired provider — exercise the
    # provider's failure path without going through ``build_app``.

    @app.get("/probe")
    def _probe(  # pragma: no cover - body unreached
        storage: IStorage = Depends(get_storage),
    ) -> dict[str, str]:
        return {"ok": "yes"}

    with TestClient(app, raise_server_exceptions=True) as client:
        with pytest.raises(RuntimeError) as exc:
            client.get("/probe")
        assert "app.state.storage" in str(exc.value)


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
