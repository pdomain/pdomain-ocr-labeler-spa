"""DI provider pins for the M2-slice-2 active-project carrier.

Verifies:

- ``bootstrap.build_app`` stashes an ``ActiveProjectCarrier`` instance
  on ``app.state.active_project_carrier`` (slice 2's wiring step).
- ``get_active_project_carrier`` returns the stashed instance via
  ``Depends``; same identity across calls (singleton per app).
- ``get_active_project`` returns ``None`` on a fresh app (carrier is
  empty by default).
- ``get_active_project`` returns a frozen ``ActiveProject`` snapshot
  after a ``set_active_project`` call.
- The unwired-app guardrail (``RuntimeError`` if ``app.state``
  attribute missing) extends to the new providers, matching the
  pattern from the existing settings / app_state / storage / auth /
  ocr providers.

Spec authority:
- ``specs/02-backend.md §6`` (DI provider shape).
- ``specs/02-backend.md §13`` (active-project lifecycle).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.api.dependencies import (
    get_active_project,
    get_active_project_carrier,
)
from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.active_project import (
    ActiveProject,
    ActiveProjectCarrier,
)
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


# ── bootstrap wiring ───────────────────────────────────────────────────────


def test_build_app_stashes_active_project_carrier(settings: Settings) -> None:
    app = build_app(settings)
    carrier = app.state.active_project_carrier
    assert isinstance(carrier, ActiveProjectCarrier)
    # Default empty: no project active, generation == 0.
    assert carrier.snapshot() is None
    assert carrier.generation == 0


def test_build_app_carrier_singleton_per_app(settings: Settings) -> None:
    """Two ``build_app`` calls produce two distinct carriers — but each
    carrier is the same identity across requests within its app.
    """
    app1 = build_app(settings)
    app2 = build_app(settings)
    assert app1.state.active_project_carrier is not app2.state.active_project_carrier


# ── get_active_project_carrier ────────────────────────────────────────────


def test_get_active_project_carrier_via_depends(client: TestClient) -> None:
    """Provider returns the stashed carrier via FastAPI's ``Depends``.

    Two requests hit the same identity — the carrier is wired once at
    app-build time and never replaced per-request.
    """
    app: FastAPI = client.app  # type: ignore[assignment]

    captured_ids: list[int] = []

    @app.get("/_probe/active_project_carrier")
    def _probe(
        carrier: ActiveProjectCarrier = Depends(get_active_project_carrier),
    ) -> dict[str, object]:
        captured_ids.append(id(carrier))
        return {"type": type(carrier).__name__}

    r1 = client.get("/_probe/active_project_carrier")
    r2 = client.get("/_probe/active_project_carrier")
    assert r1.status_code == 200
    assert r1.json() == {"type": "ActiveProjectCarrier"}
    assert r2.status_code == 200
    assert captured_ids[0] == captured_ids[1]
    # And it's the SAME identity as what's on app.state.
    assert captured_ids[0] == id(app.state.active_project_carrier)


# ── get_active_project (snapshot) ──────────────────────────────────────────


def test_get_active_project_returns_none_on_fresh_app(client: TestClient) -> None:
    app: FastAPI = client.app  # type: ignore[assignment]

    @app.get("/_probe/active_project")
    def _probe(
        snap: ActiveProject | None = Depends(get_active_project),
    ) -> dict[str, object]:
        return {"snap_is_none": snap is None}

    r = client.get("/_probe/active_project")
    assert r.status_code == 200
    assert r.json() == {"snap_is_none": True}


def test_get_active_project_returns_snapshot_after_swap(client: TestClient, tmp_path: Path) -> None:
    """After a ``set_active_project`` on the carrier, the snapshot
    provider returns the frozen snapshot."""
    app: FastAPI = client.app  # type: ignore[assignment]

    @app.get("/_probe/active_project_path")
    def _probe(
        snap: ActiveProject | None = Depends(get_active_project),
    ) -> dict[str, object]:
        return {
            "path": str(snap.path) if snap else None,
            "label": snap.label if snap else None,
        }

    proj = tmp_path / "myproj"
    proj.mkdir()
    app.state.active_project_carrier.set_active_project(proj)

    r = client.get("/_probe/active_project_path")
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == str(proj.resolve())
    assert body["label"] == "myproj"


# ── unwired-app guardrail ──────────────────────────────────────────────────


def test_get_active_project_carrier_raises_on_unwired_app() -> None:
    """A bare ``FastAPI()`` (someone forgot ``build_app``) must produce
    a wiring-clear ``RuntimeError`` from the provider."""
    bare_app = FastAPI()

    @bare_app.get("/_probe/carrier")
    def _probe(
        carrier: ActiveProjectCarrier = Depends(get_active_project_carrier),
    ) -> dict[str, object]:  # pragma: no cover - never reached
        return {"ok": True}

    with TestClient(bare_app, raise_server_exceptions=True) as c:
        with pytest.raises(RuntimeError, match="active_project_carrier"):
            c.get("/_probe/carrier")


def test_get_active_project_raises_on_unwired_app() -> None:
    """The snapshot helper inherits the same wiring guardrail
    (it reaches through ``get_active_project_carrier``)."""
    bare_app = FastAPI()

    @bare_app.get("/_probe/active")
    def _probe(
        snap: ActiveProject | None = Depends(get_active_project),
    ) -> dict[str, object]:  # pragma: no cover - never reached
        return {"ok": True}

    with TestClient(bare_app, raise_server_exceptions=True) as c:
        with pytest.raises(RuntimeError, match="active_project_carrier"):
            c.get("/_probe/active")
