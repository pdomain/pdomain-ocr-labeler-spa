"""M3 slice 8a/8c-i/8c-iii-c acceptance: ``api/ocr_config.py`` router
wires the iter-7 OCR config DTOs into the public HTTP surface.

Spec authority:

- ``specs/02-backend.md §5.8`` lines 317-322 — endpoint contracts
  (``GET /api/ocr-config``, ``POST /api/ocr-config/models``,
  ``POST /api/ocr-config/rescan``).
- ``specs/01-data-models.md §`` lines 374-400 — wire shapes
  (``OCRModelOption``, ``GetOCRConfigResponse``,
  ``SetOCRModelsRequest``).

What slice 8a shipped:

1. ``GET /api/ocr-config`` returns a ``GetOCRConfigResponse``-shaped
   payload composed from the iter-7 DTOs.
2. The route is ``include_in_schema=True`` because OpenAPI export
   (``make openapi-export``) drives the frontend ``types.ts``.

What slice 8c-i added: stateless ``POST /api/ocr-config/models`` echo
with stock-only key validation.

What slice 8c-iii-c adds: ``selection_reason`` is now derived from
``core.model_selection.pick_default_keys`` over a discovery-pipeline
record list (HF probe + local-models walk), not the previously
hardcoded ``"stock-fallback"``. The option lists remain stock-only;
surfacing HF / local options is slice 8c-iv+ work.

**Test isolation pin (slice 8c-iii-c).** The router's discovery
defaults reach the real Hugging Face hub when ``huggingface_hub`` is
importable + network is up — that's the production contract. To keep
this integration suite deterministic, the ``client`` fixture
monkeypatches the router's HF probe + local-models-root to no-network
defaults: probe → ``None``, root → empty tmpdir, picker → ``stock-fallback``.
Tests that need a different reason install their own monkeypatches
*after* the fixture (e.g. ``test_get_ocr_config_returns_hf_latest_when_hub_reachable``).

Slice 8c-iii-c deliberately does NOT:

- Implement ``POST /api/ocr-config/rescan``.
- Persist a selection. The route is stateless in this slice.
- Surface HF or local options into ``detection_options`` /
  ``recognition_options``. The picker may pick non-stock keys, but
  ``selected_*`` and the option lists stay stock-only — what changes
  is ``selection_reason``. (Slice 8c-iv+ wires the carrier + persistence.)
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[arg-type]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Build a TestClient with discovery pipeline pinned to no-network defaults.

    The slice-8c-iii-c default behavior (probe HF, walk local-models
    dir) is honest in production but non-deterministic in tests: the
    sandbox may or may not have ``huggingface_hub`` installed and may
    or may not be online. Pin both axes so the suite is hermetic by
    default; tests that exercise a non-default ``selection_reason``
    install their own monkeypatches *after* this fixture.
    """
    from pd_ocr_labeler_spa.api import ocr_config as _ocr_config_mod

    monkeypatch.setattr(_ocr_config_mod, "fetch_hf_last_modified", lambda: None)
    empty_root = tmp_path / "no-models"  # not created → discover_local_pairs returns []
    monkeypatch.setattr(_ocr_config_mod, "_resolve_local_models_root", lambda: empty_root)

    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        yield c


# ──────────────────────────────────────────────────────────────────────
# GET /api/ocr-config
# ──────────────────────────────────────────────────────────────────────


def test_get_ocr_config_returns_200(client: TestClient) -> None:
    """The route exists at the spec-canonical URL."""
    resp = client.get("/api/ocr-config")
    assert resp.status_code == 200, resp.text


def test_get_ocr_config_payload_validates_against_dto(client: TestClient) -> None:
    """Response body parses cleanly into ``GetOCRConfigResponse``.

    This is the first-line spec contract: anything that doesn't validate
    against the iter-7 DTO is a wire-shape break.
    """
    from pd_ocr_labeler_spa.core.ocr_models import GetOCRConfigResponse

    resp = client.get("/api/ocr-config")
    parsed = GetOCRConfigResponse.model_validate(resp.json())
    # Spec-mandated invariants:
    assert isinstance(parsed.detection_options, list)
    assert isinstance(parsed.recognition_options, list)
    assert parsed.selected_detection
    assert parsed.selected_recognition


def test_get_ocr_config_default_reason_is_hf_unreachable_no_local(
    client: TestClient,
) -> None:
    """In the no-network/no-local-models default fixture, the picker's
    honest answer is ``"hf-unreachable-no-local"``.

    The fixture monkeypatches ``fetch_hf_last_modified`` → ``None`` and
    points the local-models walk at an empty tmpdir. ``_gather_records``
    still emits an HF record (so the picker can decide between
    ``hf-latest`` / ``hf-unreachable-no-local`` / etc.), but with
    ``hf_last_modified=None`` the picker recognises the HF entry as
    unreachable and there's no local pair → spec-literal
    ``"hf-unreachable-no-local"``. Pre-slice-8c-iii-c this test pinned
    the iter-10 hardcoded ``"stock-fallback"``; the rename + relaxation
    is the slice-8c-iii-c shift from "hardcoded reason" to "real
    selection."

    The selected key for both lists points into the options list of
    the same kind — the modal can't render a selection that doesn't
    exist as an option.
    """
    resp = client.get("/api/ocr-config")
    body = resp.json()
    assert body["selection_reason"] == "hf-unreachable-no-local"
    det_keys = {opt["key"] for opt in body["detection_options"]}
    rec_keys = {opt["key"] for opt in body["recognition_options"]}
    assert body["selected_detection"] in det_keys
    assert body["selected_recognition"] in rec_keys


def test_get_ocr_config_surfaces_stock_and_hf_options_by_default(
    client: TestClient,
) -> None:
    """Slice 8c-v-a: option lists surface stock + HF (always),
    plus zero-or-more local pairs from discovery.

    Legacy parity (legacy ``model_selection_operations.py`` line 351):
    the HF option is *always* present even when the hub is unreachable —
    the user can still pick it and get a "would use HF if online" UX
    affordance. With the no-network fixture (HF probe → ``None``, empty
    local-models root), the option lists therefore contain exactly stock
    + huggingface, both for detection and recognition.
    """
    resp = client.get("/api/ocr-config")
    body = resp.json()
    for label, options in (
        ("detection_options", body["detection_options"]),
        ("recognition_options", body["recognition_options"]),
    ):
        sources = [opt["source"] for opt in options]
        assert "stock" in sources, (label, options)
        assert "huggingface" in sources, (label, options)
        # In the empty-local-tree fixture, no local options expected.
        assert "local" not in sources, (label, options)


def test_get_ocr_config_hf_option_uses_legacy_label(client: TestClient) -> None:
    """HF option label mirrors legacy
    ``f"Hugging Face: {HF_DEFAULT_REPO} (latest)"`` (legacy line 353)
    so the modal renders the same string operators are used to.
    """
    from pd_ocr_labeler_spa.core.hf_probe import HF_DEFAULT_REPO

    resp = client.get("/api/ocr-config")
    body = resp.json()
    expected_label = f"Hugging Face: {HF_DEFAULT_REPO} (latest)"
    for options in (body["detection_options"], body["recognition_options"]):
        hf = next((o for o in options if o["source"] == "huggingface"), None)
        assert hf is not None
        assert hf["key"] == "huggingface"
        assert hf["label"] == expected_label


def test_get_ocr_config_surfaces_local_pairs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slice 8c-v-a: a discovered local pair surfaces as one option in
    each list with ``source="local"`` and ``key="<profile>/<signature>"``.

    Legacy label parity (legacy line 288): ``f"{profile}: {signature}"``.
    """
    from pd_ocr_labeler_spa.api import ocr_config as _ocr_config_mod

    profile = tmp_path / "models" / "all"
    (profile / "detection").mkdir(parents=True)
    (profile / "recognition").mkdir(parents=True)
    (profile / "detection" / "all-detection-base-1700000000.pt").write_bytes(b"x")
    (profile / "recognition" / "all-recognition-base-1700000000.pt").write_bytes(b"x")

    monkeypatch.setattr(_ocr_config_mod, "fetch_hf_last_modified", lambda: None)
    monkeypatch.setattr(_ocr_config_mod, "_resolve_local_models_root", lambda: tmp_path / "models")

    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        body = c.get("/api/ocr-config").json()

    for options in (body["detection_options"], body["recognition_options"]):
        local = next((o for o in options if o["source"] == "local"), None)
        assert local is not None, options
        assert local["key"] == "all/all-base-1700000000"
        assert local["label"] == "all: all-base-1700000000"


def test_post_ocr_config_models_accepts_huggingface_key(client: TestClient) -> None:
    """Slice 8c-v-a: POST accepts ``"huggingface"`` as detection/recognition
    key now that the option list surfaces it. Pre-slice the only valid key
    was ``"stock"`` (legacy POST 400 → still applies for unknown keys).
    """
    resp = client.post(
        "/api/ocr-config/models",
        json={
            "detection_key": "huggingface",
            "recognition_key": "huggingface",
            "hf_pinned_revision": None,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["selected_detection"] == "huggingface"
    assert body["selected_recognition"] == "huggingface"


def test_post_ocr_config_models_accepts_discovered_local_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slice 8c-v-a: a key surfaced as a local option may be POSTed."""
    from pd_ocr_labeler_spa.api import ocr_config as _ocr_config_mod

    profile = tmp_path / "models" / "all"
    (profile / "detection").mkdir(parents=True)
    (profile / "recognition").mkdir(parents=True)
    (profile / "detection" / "all-detection-base-1700000000.pt").write_bytes(b"x")
    (profile / "recognition" / "all-recognition-base-1700000000.pt").write_bytes(b"x")

    monkeypatch.setattr(_ocr_config_mod, "fetch_hf_last_modified", lambda: None)
    monkeypatch.setattr(_ocr_config_mod, "_resolve_local_models_root", lambda: tmp_path / "models")

    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        local_key = "all/all-base-1700000000"
        resp = c.post(
            "/api/ocr-config/models",
            json={
                "detection_key": local_key,
                "recognition_key": local_key,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["selected_detection"] == local_key
        assert body["selected_recognition"] == local_key


def test_get_ocr_config_hf_pinned_revision_unset(client: TestClient) -> None:
    """``hf_pinned_revision`` is ``None`` when no HF model is selected.

    Spec line 390 declares the field ``str | None``; with stock-only
    options there's no HF revision to surface. Future slices that
    surface a default HF model would emit a real revision string
    here — until then, ``None`` is the only honest value.
    """
    resp = client.get("/api/ocr-config")
    body = resp.json()
    assert body["hf_pinned_revision"] is None


def test_get_ocr_config_appears_in_openapi_schema(client: TestClient) -> None:
    """``GET /api/ocr-config`` surfaces in OpenAPI for ``types.ts`` gen.

    ``make openapi-export`` walks the OpenAPI doc to emit
    ``frontend/src/api/types.ts``; an accidentally
    ``include_in_schema=False`` route would silently break the SPA's
    types contract.
    """
    spec = client.get("/openapi.json").json()
    assert "/api/ocr-config" in spec["paths"]
    assert "get" in spec["paths"]["/api/ocr-config"]


# ──────────────────────────────────────────────────────────────────────
# POST /api/ocr-config/models — slice 8c-i (stateless echo)
# ──────────────────────────────────────────────────────────────────────
#
# Slice 8c-i ships the route shape — same DTO contract as GET — but
# without a persistent OCRConfigCarrier yet. The handler validates
# requested keys against the slice-8a stock-fallback option lists and
# echoes a GetOCRConfigResponse with ``selected_*`` set from the
# request body. Unknown keys → 400. ``selection_reason`` stays
# ``"stock-fallback"`` because no real probing exists yet (slice 8c-ii+
# work). When carrier-backed selection state lands, this test file gets
# extended to verify persistence; the route shape stays the same.


def test_post_ocr_config_models_returns_200_for_known_keys(client: TestClient) -> None:
    """The route exists at the spec-canonical URL and accepts the
    iter-7 ``SetOCRModelsRequest`` body."""
    resp = client.post(
        "/api/ocr-config/models",
        json={
            "detection_key": "stock",
            "recognition_key": "stock",
            "hf_pinned_revision": None,
        },
    )
    assert resp.status_code == 200, resp.text


def test_post_ocr_config_models_response_validates_against_dto(
    client: TestClient,
) -> None:
    """Response body parses cleanly into ``GetOCRConfigResponse``.

    Spec §5.8 line 320 declares the POST returns the same DTO as GET so
    the frontend can refresh from a single shape.
    """
    from pd_ocr_labeler_spa.core.ocr_models import GetOCRConfigResponse

    resp = client.post(
        "/api/ocr-config/models",
        json={"detection_key": "stock", "recognition_key": "stock"},
    )
    parsed = GetOCRConfigResponse.model_validate(resp.json())
    assert parsed.selected_detection == "stock"
    assert parsed.selected_recognition == "stock"


def test_post_ocr_config_models_echoes_selected_keys(client: TestClient) -> None:
    """``selected_detection`` and ``selected_recognition`` reflect the
    request body, not a hardcoded default. Future slices that add
    non-stock options must keep this round-trip property."""
    resp = client.post(
        "/api/ocr-config/models",
        json={"detection_key": "stock", "recognition_key": "stock"},
    )
    body = resp.json()
    assert body["selected_detection"] == "stock"
    assert body["selected_recognition"] == "stock"


def test_post_ocr_config_models_unknown_detection_key_returns_400(
    client: TestClient,
) -> None:
    """Unknown detection key → 400 — slice 8a's stock-only option list
    means anything else is a contract violation. Future slices that
    discover real models will widen the accept-set; this test gets
    relaxed when that lands."""
    resp = client.post(
        "/api/ocr-config/models",
        json={"detection_key": "hf:unknown", "recognition_key": "stock"},
    )
    assert resp.status_code == 400, resp.text


def test_post_ocr_config_models_unknown_recognition_key_returns_400(
    client: TestClient,
) -> None:
    """Unknown recognition key → 400 — same reasoning as detection."""
    resp = client.post(
        "/api/ocr-config/models",
        json={"detection_key": "stock", "recognition_key": "local:/no/such"},
    )
    assert resp.status_code == 400, resp.text


def test_post_ocr_config_models_extra_field_rejected_with_validation_error(
    client: TestClient,
) -> None:
    """``SetOCRModelsRequest`` is ``extra="forbid"`` — a stray key
    surfaces through the project's validation_error envelope (HTTP 400
    with ``error="validation_error"``, ``details[*].type=="extra_forbidden"``).
    The status code is 400 rather than the FastAPI default 422 because
    the app installs a unified validation-error handler — see
    ``api/middleware/validation_error.py`` (or equivalent). Pins the
    iter-7 DTO contract end-to-end through the route."""
    resp = client.post(
        "/api/ocr-config/models",
        json={
            "detection_key": "stock",
            "recognition_key": "stock",
            "rogue_field": "nope",
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "validation_error"
    types = {d["type"] for d in body["details"]}
    assert "extra_forbidden" in types


def test_post_ocr_config_models_uses_picker_for_selection_reason(
    client: TestClient,
) -> None:
    """``selection_reason`` is the picker's output, not a hardcoded value.

    With the fixture's no-network/no-local default, the picker returns
    ``"hf-unreachable-no-local"``. Slice 8c-iii-c moved this from the
    iter-10 hardcoded ``"stock-fallback"`` to the discovery-pipeline
    pick — this test pins the wiring (POST goes through the same
    ``_build_snapshot`` as GET so reasons agree).
    """
    resp = client.post(
        "/api/ocr-config/models",
        json={"detection_key": "stock", "recognition_key": "stock"},
    )
    body = resp.json()
    assert body["selection_reason"] == "hf-unreachable-no-local"


def test_post_ocr_config_models_appears_in_openapi_schema(
    client: TestClient,
) -> None:
    """``POST /api/ocr-config/models`` surfaces in OpenAPI so
    ``make openapi-export`` regenerates ``types.ts``. Without this,
    the frontend mutation hook can't be typed against the same DTO.
    """
    spec = client.get("/openapi.json").json()
    assert "/api/ocr-config/models" in spec["paths"]
    assert "post" in spec["paths"]["/api/ocr-config/models"]


# ──────────────────────────────────────────────────────────────────────
# Slice 8c-iii-c — discovery pipeline drives ``selection_reason``
# ──────────────────────────────────────────────────────────────────────


def test_get_ocr_config_returns_hf_latest_when_hub_reachable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the HF probe returns a timestamp and there are no local
    pairs, the picker reports ``"hf-latest"``. Pins the slice-8c-iii-c
    wiring of ``fetch_hf_last_modified`` into ``_build_snapshot``.

    Builds its own client (rather than using the module-level fixture)
    so the HF-probe monkeypatch wins over the fixture's no-network
    default; otherwise fixture-applied patches would shadow this test's
    intent.
    """
    from datetime import UTC, datetime

    from pd_ocr_labeler_spa.api import ocr_config as _ocr_config_mod

    fixed = datetime(2025, 6, 1, tzinfo=UTC)
    monkeypatch.setattr(_ocr_config_mod, "fetch_hf_last_modified", lambda: fixed)
    empty_root = tmp_path / "no-models"
    monkeypatch.setattr(_ocr_config_mod, "_resolve_local_models_root", lambda: empty_root)

    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.get("/api/ocr-config")
    body = resp.json()
    assert body["selection_reason"] == "hf-latest"


def test_get_ocr_config_returns_local_only_when_hub_offline_and_pair_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HF probe returns ``None`` AND a complete local pair exists →
    picker returns ``"local-only-hf-unreachable"``. Pins the wiring
    of ``discover_local_pairs`` into ``_build_snapshot``: the function
    is actually called with ``_resolve_local_models_root()``'s output,
    its records flow into ``pick_default_keys``, and the resulting
    reason reaches the wire.
    """
    from pd_ocr_labeler_spa.api import ocr_config as _ocr_config_mod

    # Build a legacy-shaped local-models tree with one complete pair.
    profile = tmp_path / "models" / "all"
    (profile / "detection").mkdir(parents=True)
    (profile / "recognition").mkdir(parents=True)
    (profile / "detection" / "all-detection-base-1700000000.pt").write_bytes(b"x")
    (profile / "recognition" / "all-recognition-base-1700000000.pt").write_bytes(b"x")

    monkeypatch.setattr(_ocr_config_mod, "fetch_hf_last_modified", lambda: None)
    monkeypatch.setattr(_ocr_config_mod, "_resolve_local_models_root", lambda: tmp_path / "models")

    settings = _make_settings(tmp_path)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.get("/api/ocr-config")
    body = resp.json()
    assert body["selection_reason"] == "local-only-hf-unreachable"


# ──────────────────────────────────────────────────────────────────────
# Slice 8c-iv-a: OCRConfigCarrier wired — POST persists into a subsequent GET
# ──────────────────────────────────────────────────────────────────────


def test_post_persists_selection_into_subsequent_get(client: TestClient) -> None:
    """A successful ``POST /api/ocr-config/models`` must be visible in
    the next ``GET /api/ocr-config`` from the same process.

    Pre-slice-8c-iv-a this test would fail: the POST was a stateless
    echo and the GET re-read defaults from ``_build_snapshot``. Slice
    8c-iv-a wires the in-process ``OCRConfigCarrier`` so the POST
    mutates ``app.state.ocr_config_carrier`` and the GET reads from it.

    (Disk-side persistence — survival across server restart — is slice
    8c-iv-b territory; this test only pins the in-process round-trip.)
    """
    # Default state pre-POST.
    resp_initial = client.get("/api/ocr-config")
    assert resp_initial.status_code == 200
    assert resp_initial.json()["selected_detection"] == "stock"
    assert resp_initial.json()["selected_recognition"] == "stock"
    assert resp_initial.json()["hf_pinned_revision"] is None

    # POST a (still-stock) selection with a non-None revision so we can
    # observe the carrier mutation through a field that defaults to None.
    resp_post = client.post(
        "/api/ocr-config/models",
        json={
            "detection_key": "stock",
            "recognition_key": "stock",
            "hf_pinned_revision": "main",
        },
    )
    assert resp_post.status_code == 200, resp_post.text
    assert resp_post.json()["hf_pinned_revision"] == "main"

    # Subsequent GET reflects the POST's selection.
    resp_after = client.get("/api/ocr-config")
    assert resp_after.status_code == 200
    body = resp_after.json()
    assert body["selected_detection"] == "stock"
    assert body["selected_recognition"] == "stock"
    assert body["hf_pinned_revision"] == "main"


def test_carrier_isolated_across_build_app_instances(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each ``build_app(settings)`` call gets its own carrier instance.

    Pins the "no module-global state" invariant: a POST against one app
    must not leak into a second app built from the same process. This
    is the test isolation contract for the carrier wire-up — the same
    contract ``ProjectState`` and ``ActiveProjectCarrier`` already pin.
    """
    from pd_ocr_labeler_spa.api import ocr_config as _ocr_config_mod

    monkeypatch.setattr(_ocr_config_mod, "fetch_hf_last_modified", lambda: None)
    monkeypatch.setattr(_ocr_config_mod, "_resolve_local_models_root", lambda: tmp_path / "no-models")

    settings_a = _make_settings(tmp_path / "a")
    settings_b = _make_settings(tmp_path / "b")

    app_a = build_app(settings_a)
    app_b = build_app(settings_b)

    with TestClient(app_a) as ca, TestClient(app_b) as cb:
        # Mutate A's carrier only.
        resp = ca.post(
            "/api/ocr-config/models",
            json={
                "detection_key": "stock",
                "recognition_key": "stock",
                "hf_pinned_revision": "rev-on-a-only",
            },
        )
        assert resp.status_code == 200
        # A reflects.
        body_a = ca.get("/api/ocr-config").json()
        assert body_a["hf_pinned_revision"] == "rev-on-a-only"
        # B unchanged — still default.
        body_b = cb.get("/api/ocr-config").json()
        assert body_b["hf_pinned_revision"] is None


def test_carrier_exposed_on_app_state(client: TestClient) -> None:
    """``app.state.ocr_config_carrier`` is the wired instance.

    Pins the ``bootstrap.build_app`` step that registers the carrier
    so the dependency provider can resolve it. Direct access for
    inspection / test seam — the production read path goes through
    ``Depends(get_ocr_config_carrier)``.
    """
    from pd_ocr_labeler_spa.core.ocr_config_state import OCRConfigCarrier

    carrier = client.app.state.ocr_config_carrier  # type: ignore[attr-defined]
    assert isinstance(carrier, OCRConfigCarrier)
    # Default state — no POST yet.
    assert carrier.snapshot() == ("stock", "stock", None)


def test_post_rejects_unknown_keys_without_mutating_carrier(
    client: TestClient,
) -> None:
    """A 400 response from key validation must NOT mutate the carrier.

    Pins the validation-before-mutation order: the carrier's
    ``set_models`` is called only after both keys pass the option-list
    gate. If the order were reversed (set first, validate later) a
    bad-key POST would leak into a subsequent GET.
    """
    # Pre-state.
    body_before = client.get("/api/ocr-config").json()
    assert body_before["selected_detection"] == "stock"

    resp = client.post(
        "/api/ocr-config/models",
        json={
            "detection_key": "not-a-real-key",
            "recognition_key": "stock",
            "hf_pinned_revision": "should-not-leak",
        },
    )
    assert resp.status_code == 400

    # Post-state unchanged.
    body_after = client.get("/api/ocr-config").json()
    assert body_after["selected_detection"] == "stock"
    assert body_after["selected_recognition"] == "stock"
    assert body_after["hf_pinned_revision"] is None


# ──────────────────────────────────────────────────────────────────────
# Slice 8c-iv-b: ocr_config.json sidecar — selection survives a restart
# ──────────────────────────────────────────────────────────────────────


def _make_settings_for_data_root(tmp_path: Path) -> Settings:
    """Variant of ``_make_settings`` that takes a tmp_path-like dir and
    derives the four roots underneath it. Used by the across-restart
    tests that need TWO separate ``build_app`` calls sharing a single
    ``data_root`` so the second app can read the first's sidecar."""
    return Settings(  # type: ignore[arg-type]
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )


def test_post_selection_persists_across_build_app_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slice 8c-iv-b acceptance pin: a POST against one ``build_app``
    instance is reflected in a fresh ``build_app`` against the same
    ``data_root``.

    This is the load-bearing test for the entire sidecar slice — the
    in-process carrier (slice 8c-iv-a) was already covered by
    ``test_post_persists_selection_into_subsequent_get``; what's new
    is that selection now survives a server-process restart via
    ``<data_root>/ocr_config.json`` (spec §7a).

    Two ``build_app(settings)`` calls share a single ``tmp_path``-rooted
    settings (so they get the same ``data_root``). The first POSTs a
    non-default ``hf_pinned_revision``; the second reads its initial
    GET and must see that revision because the lifespan startup hook
    seeded the carrier from the sidecar on disk.
    """
    from pd_ocr_labeler_spa.api import ocr_config as _ocr_config_mod

    monkeypatch.setattr(_ocr_config_mod, "fetch_hf_last_modified", lambda: None)
    monkeypatch.setattr(_ocr_config_mod, "_resolve_local_models_root", lambda: tmp_path / "no-models")

    settings = _make_settings_for_data_root(tmp_path)

    # First "process": POST a selection.
    app1 = build_app(settings)
    with TestClient(app1) as c1:
        resp = c1.post(
            "/api/ocr-config/models",
            json={
                "detection_key": "stock",
                "recognition_key": "stock",
                "hf_pinned_revision": "pinned-via-restart-test",
            },
        )
        assert resp.status_code == 200, resp.text
        # Sidecar file landed where the spec puts it.
        sidecar = settings.data_root / "ocr_config.json"
        assert sidecar.exists(), "POST should have written ocr_config.json under data_root"

    # Second "process": fresh build_app, same data_root. Lifespan
    # startup hook reads the sidecar and seeds the new carrier.
    app2 = build_app(settings)
    with TestClient(app2) as c2:
        body = c2.get("/api/ocr-config").json()
        assert body["selected_detection"] == "stock"
        assert body["selected_recognition"] == "stock"
        assert body["hf_pinned_revision"] == "pinned-via-restart-test", (
            "Lifespan startup hook must seed OCRConfigCarrier from <data_root>/ocr_config.json (spec §7a)."
        )


def test_idempotent_post_does_not_rewrite_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An idempotent re-POST of the same triple must not touch the sidecar.

    Pins the ``carrier.set_models`` returns-True-iff-changed contract
    the slice depends on: re-POSTing the same selection is a no-op
    (no new mtime, no rewrite). Otherwise a busy SPA could thrash the
    disk on every UI re-mount.
    """
    from pd_ocr_labeler_spa.api import ocr_config as _ocr_config_mod

    monkeypatch.setattr(_ocr_config_mod, "fetch_hf_last_modified", lambda: None)
    monkeypatch.setattr(_ocr_config_mod, "_resolve_local_models_root", lambda: tmp_path / "no-models")

    settings = _make_settings_for_data_root(tmp_path)
    sidecar = settings.data_root / "ocr_config.json"

    app = build_app(settings)
    with TestClient(app) as c:
        # First POST — a real change (revision goes None → "v1").
        resp1 = c.post(
            "/api/ocr-config/models",
            json={
                "detection_key": "stock",
                "recognition_key": "stock",
                "hf_pinned_revision": "v1",
            },
        )
        assert resp1.status_code == 200
        assert sidecar.exists()
        first_mtime_ns = sidecar.stat().st_mtime_ns

        # Second POST — same triple. carrier.set_models returns False;
        # save_ocr_config is NOT called; sidecar mtime unchanged.
        resp2 = c.post(
            "/api/ocr-config/models",
            json={
                "detection_key": "stock",
                "recognition_key": "stock",
                "hf_pinned_revision": "v1",
            },
        )
        assert resp2.status_code == 200
        second_mtime_ns = sidecar.stat().st_mtime_ns
        assert second_mtime_ns == first_mtime_ns, (
            "Idempotent re-POST should skip the sidecar write — carrier.set_models "
            "returns False on no-op and the route gates save() on that flag."
        )


def test_corrupt_sidecar_does_not_crash_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A corrupt ``ocr_config.json`` must not crash startup.

    Spec §7a load-failure contract: every failure path returns ``None``
    and the carrier keeps its construction-time defaults. Pin this at
    the integration boundary (not just the unit one) because startup
    happens inside ``TestClient(app) as ...`` — a regression that
    raises here would crash the test client.
    """
    from pd_ocr_labeler_spa.api import ocr_config as _ocr_config_mod

    monkeypatch.setattr(_ocr_config_mod, "fetch_hf_last_modified", lambda: None)
    monkeypatch.setattr(_ocr_config_mod, "_resolve_local_models_root", lambda: tmp_path / "no-models")

    settings = _make_settings_for_data_root(tmp_path)
    settings.data_root.mkdir(parents=True, exist_ok=True)
    (settings.data_root / "ocr_config.json").write_text("this is { not valid json", encoding="utf-8")

    app = build_app(settings)
    with TestClient(app) as c:
        # Startup completed; GET returns defaults (carrier was NOT seeded
        # because the sidecar read failed).
        body = c.get("/api/ocr-config").json()
        assert body["selected_detection"] == "stock"
        assert body["selected_recognition"] == "stock"
        assert body["hf_pinned_revision"] is None
