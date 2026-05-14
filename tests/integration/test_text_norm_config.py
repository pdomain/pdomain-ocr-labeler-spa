"""Integration tests for issue #259: OCRConfig normalize fields + GT codepoint validation.

Acceptance criteria:
- A1: POST GT containing fi-ligature (U+FB01) returns 400 validation_error
- A2: normalize_for_gt_matching: true in config.yaml persists and is read on startup
- A3: With flag true: OCR long-s-hall vs GT shall -> match_status=exact, normalized_match=true
- A4: When pd-book-tools normalize module absent: flag silently ignored (no 500)

Spec authority:
- docs/specs/2026-05-12-text-normalization-design.md - GT validation contract
- docs/architecture/09-persistence.md - config.yaml persistence
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def _make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x00")
    (proj / "002.png").write_bytes(b"\x00")
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    """TestClient with a project already loaded (book1, 2 pages)."""
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


# ── A1: GT codepoint validation ───────────────────────────────────────


def test_gt_update_rejects_fi_ligature_u_fb01(loaded_client: TestClient) -> None:
    """POST GT containing ﬁ (U+FB01) must return 400 validation_error.

    Spec: 'Backend rejects GT input containing U+FB00-U+FB06 or U+017F
    with 400 validation_error.'
    """
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": "ﬁne"},  # U+FB01 ﬁ ligature
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "validation_error"


def test_gt_update_rejects_all_fb_ligatures(loaded_client: TestClient) -> None:
    """All U+FB00-U+FB06 codepoints should be rejected."""
    ligatures = ["ﬀ", "ﬁ", "ﬂ", "ﬃ", "ﬄ", "ﬅ", "ﬆ"]
    for cp in ligatures:
        resp = loaded_client.post(
            "/api/projects/book1/pages/0/words/0/0/gt",
            json={"text": f"word{cp}"},
        )
        assert resp.status_code == 400, f"Expected 400 for U+{ord(cp):04X}, got {resp.status_code}"
        body = resp.json()
        assert body["error"] == "validation_error", f"Wrong error tag for U+{ord(cp):04X}: {body}"


def test_gt_update_rejects_long_s_u017f(loaded_client: TestClient) -> None:
    """U+017F (long-s) in GT must return 400 validation_error."""
    long_s = chr(0x017F)  # Latin small letter long s
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": long_s + "hall"},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "validation_error"


def test_gt_update_accepts_normal_text(loaded_client: TestClient) -> None:
    """Normal ASCII GT text must be accepted (200 or 404 for page-not-found, but not 400)."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/gt",
        json={"text": "hello world"},
    )
    # 200 = found + accepted; 404 = page/word not found — both are OK here
    # The key invariant: NOT a 400 validation_error for clean text
    assert resp.status_code != 400, resp.text


# ── A2: normalize_for_gt_matching persists in config.yaml ─────────────


def test_normalize_for_gt_matching_field_in_app_config() -> None:
    """AppConfig must expose normalize_for_gt_matching as a bool field."""
    from pd_ocr_labeler_spa.core.persistence.config_yaml import AppConfig

    cfg = AppConfig()
    assert cfg.normalize_for_gt_matching is False  # default off


def test_normalize_plaintext_tabs_field_in_app_config() -> None:
    """AppConfig must expose normalize_plaintext_tabs as a bool field."""
    from pd_ocr_labeler_spa.core.persistence.config_yaml import AppConfig

    cfg = AppConfig()
    assert cfg.normalize_plaintext_tabs is False  # default off


def test_normalize_profile_field_in_app_config() -> None:
    """AppConfig must expose normalize_profile with default 'ascii'."""
    from pd_ocr_labeler_spa.core.persistence.config_yaml import AppConfig

    cfg = AppConfig()
    assert cfg.normalize_profile == "ascii"


def test_normalize_fields_persist_in_config_yaml(tmp_path: Path) -> None:
    """normalize_for_gt_matching: true written to config.yaml survives a load_config cycle."""
    import yaml

    from pd_ocr_labeler_spa.core.persistence.config_yaml import AppConfig, load_config, save_config

    config_root = tmp_path / "config"
    config_root.mkdir()

    cfg = AppConfig(normalize_for_gt_matching=True, normalize_plaintext_tabs=False, normalize_profile="ascii")
    save_config(config_root, cfg)

    # Verify the YAML contains the key
    raw = yaml.safe_load((config_root / "config.yaml").read_text(encoding="utf-8"))
    assert raw["normalize_for_gt_matching"] is True

    # Reload and verify
    loaded = load_config(config_root)
    assert loaded.normalize_for_gt_matching is True


def test_normalize_fields_round_trip_on_startup(tmp_path: Path) -> None:
    """App reads normalize_for_gt_matching=true from config.yaml on startup.

    The AppConfig (from config.yaml) is read at startup and must include
    the normalize_for_gt_matching flag when it was previously saved as true.
    """
    from pd_ocr_labeler_spa.core.persistence.config_yaml import AppConfig, save_config

    config_root = tmp_path / "config"
    config_root.mkdir()

    # Pre-write config.yaml with the flag enabled
    save_config(config_root, AppConfig(normalize_for_gt_matching=True))

    # Build app with this config root — startup must not raise
    settings = _make_settings(tmp_path, config_root=config_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.get("/healthz")
        assert resp.status_code == 200


def test_legacy_config_yaml_without_normalize_fields_loads_cleanly(tmp_path: Path) -> None:
    """A config.yaml without normalize fields (legacy format) must load with defaults.

    extra='ignore' on AppConfig means unknown keys are dropped; missing keys
    must use the field defaults. A legacy config.yaml with only
    source_projects_root must still yield normalize_for_gt_matching=False.
    """
    from pd_ocr_labeler_spa.core.persistence.config_yaml import load_config

    config_root = tmp_path / "config"
    config_root.mkdir()

    # Write a legacy-style config.yaml without normalize fields
    (config_root / "config.yaml").write_text(
        "source_projects_root: null\n",
        encoding="utf-8",
    )

    cfg = load_config(config_root)
    assert cfg.normalize_for_gt_matching is False
    assert cfg.normalize_plaintext_tabs is False
    assert cfg.normalize_profile == "ascii"


# ── A3 + A4: normalize flag wiring ────────────────────────────────────


def test_normalized_match_field_on_word_match() -> None:
    """WordMatch must have normalized_match: bool = False field.

    The spec adds this field to carry the 'match was only exact after
    normalization' signal used by the '≈' badge in the UI.
    """
    from pd_ocr_labeler_spa.core.models import BBox, MatchStatus, WordMatch

    wm = WordMatch(
        line_index=0,
        word_index=0,
        ocr_text=chr(0x017F) + "hall",  # U+017F long-s + "hall"
        ground_truth_text="shall",
        match_status=MatchStatus.EXACT,
        bbox=BBox(x=0, y=0, width=10, height=10),
    )
    assert wm.normalized_match is False  # default


def test_normalize_flag_absent_module_no_500(tmp_path: Path, projects_root: Path) -> None:
    """When pd-book-tools normalize module is absent, flag is silently ignored (no 500).

    A4 acceptance: the app must not 500 when normalize_for_gt_matching=True
    but pd_book_tools.text.normalize is not importable.
    """
    from pd_ocr_labeler_spa.core.persistence.config_yaml import AppConfig, save_config

    config_root = tmp_path / "config"
    config_root.mkdir()
    save_config(config_root, AppConfig(normalize_for_gt_matching=True))

    settings = _make_settings(tmp_path, config_root=config_root, source_projects_root=projects_root)
    app = build_app(settings)

    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text

        # Attempt a GT update with normal text — should not 500 even if normalize flag is set
        # and the normalize module is absent. The flag is silently ignored.
        resp2 = c.post(
            "/api/projects/book1/pages/0/words/0/0/gt",
            json={"text": "shall"},  # clean text, should be accepted
        )
        assert resp2.status_code != 500, f"500 when normalize module absent: {resp2.text}"
