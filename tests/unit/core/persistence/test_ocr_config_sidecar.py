"""Round-trip + failure-mode pins for ``core/persistence/ocr_config.py``.

Spec: ``specs/09-persistence.md §7a`` + ``specs/01-data-models.md`` (the
``ocr_config.json`` cross-ref).

This is the M3 slice 8c-iv-b filesystem sidecar that backs
``OCRConfigCarrier`` (slice 8c-iv-a). Unlike ``session_state.json``,
``ocr_config.json`` is **SPA-only** — legacy ``pd-ocr-labeler`` does not
read or write it. So the tests pin:

- Field names match the wire DTOs (``selected_detection_key``,
  ``selected_recognition_key``, ``hf_pinned_revision``).
- ``schema_version`` is the **string** ``"1.0"`` (parity with §6).
- Cold-start (file missing) → ``None``; caller seeds carrier with
  defaults.
- Failure modes (malformed JSON, wrong shape, validation failure) →
  ``None``. Startup never crashes on a corrupt sidecar.
- Save atomicity (``tmp + replace``); no stray ``.tmp`` on success.
- Save errors are **logged-and-swallowed** with stable substring
  ``ocr_config_save_failed`` — distinct from session_state's re-raise
  policy (rationale in spec §7a: a failed sidecar save must NOT turn a
  200 OCR-config POST into a 500 — the in-process carrier is the
  authoritative source-of-truth for the live session).
- Extras-tolerance (extra="ignore") + WARNING substring
  ``ocr_config_extras_dropped`` for forward-compat drift detection.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from pd_ocr_labeler_spa.core.persistence.ocr_config import (
    OCR_CONFIG_FILENAME,
    OCR_CONFIG_SCHEMA_VERSION,
    OCRConfigSidecar,
    load_ocr_config,
    save_ocr_config,
)
from pd_ocr_labeler_spa.core.persistence.paths import ocr_config_path

# ── module-level constants ───────────────────────────────────────────────


def test_constants_match_spec() -> None:
    """Spec §7a: filename ``ocr_config.json``, schema version string ``"1.0"``."""
    assert OCR_CONFIG_FILENAME == "ocr_config.json"
    assert OCR_CONFIG_SCHEMA_VERSION == "1.0"
    assert isinstance(OCR_CONFIG_SCHEMA_VERSION, str)


def test_path_helper_returns_data_root_sibling(tmp_path: Path) -> None:
    """Spec §7a: file lives at ``<data_root>/ocr_config.json``."""
    assert ocr_config_path(tmp_path) == tmp_path / "ocr_config.json"


# ── OCRConfigSidecar model ───────────────────────────────────────────────


def test_default_construction_matches_carrier_defaults() -> None:
    """Defaults must mirror ``OCRConfigCarrier()`` (slice 8c-iv-a):
    detection=stock, recognition=stock, revision=None. Otherwise a
    cold-start save would reseed the carrier with non-default values."""
    s = OCRConfigSidecar()
    assert s.schema_version == "1.0"
    assert s.selected_detection_key == "stock"
    assert s.selected_recognition_key == "stock"
    assert s.hf_pinned_revision is None


def test_field_names() -> None:
    """Spec-pin: field names match the wire DTOs (slice-8c-i
    ``SetOCRModelsRequest`` / slice-8c-i ``GetOCRConfigResponse``).
    M9.2 adds ``auto_rotate_on_load`` and ``auto_rotate_method``."""
    fields = set(OCRConfigSidecar.model_fields.keys())
    assert fields == {
        "schema_version",
        "selected_detection_key",
        "selected_recognition_key",
        "hf_pinned_revision",
        "auto_rotate_on_load",
        "auto_rotate_method",
    }


def test_rejects_non_string_keys() -> None:
    """Pydantic validation: keys must be strings (the carrier holds
    strings; the sidecar persists strings)."""
    with pytest.raises(ValidationError):
        OCRConfigSidecar(selected_detection_key=123)  # type: ignore[arg-type]


def test_ignores_extra_fields() -> None:
    """Spec §7a: ``extra="ignore"`` (forward-compat for future SPA
    versions adding additive fields). The operator-facing WARNING is
    emitted by ``load_ocr_config`` (asserted separately)."""
    s = OCRConfigSidecar.model_validate(
        {
            "selected_detection_key": "stock",
            "selected_recognition_key": "stock",
            "hf_pinned_revision": None,
            "future_field": True,
        }
    )
    assert s.selected_detection_key == "stock"
    assert not hasattr(s, "future_field")


# ── cold-start / failure-mode load behaviour ─────────────────────────────


def test_load_returns_none_when_file_missing(tmp_path: Path) -> None:
    """Cold start → ``None``. Caller seeds carrier with defaults."""
    assert load_ocr_config(tmp_path) is None


def test_load_returns_none_when_data_root_does_not_exist(tmp_path: Path) -> None:
    """Pathological cold-start: data root not yet on disk → ``None``."""
    nonexistent = tmp_path / "no-such-data-root"
    assert load_ocr_config(nonexistent) is None


def test_load_returns_none_when_file_is_unparseable_json(tmp_path: Path) -> None:
    """Corrupt file → ``None`` (logged at debug; don't crash startup)."""
    path = ocr_config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("this is not { json", encoding="utf-8")
    assert load_ocr_config(tmp_path) is None


def test_load_returns_none_when_json_is_not_an_object(tmp_path: Path) -> None:
    """Wrong top-level shape → ``None``."""
    path = ocr_config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_ocr_config(tmp_path) is None


def test_load_returns_none_on_validation_failure(tmp_path: Path) -> None:
    """Pydantic-rejected payload → ``None`` (e.g. integer where string expected)."""
    path = ocr_config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "selected_detection_key": 123,
                "selected_recognition_key": "stock",
                "hf_pinned_revision": None,
            }
        ),
        encoding="utf-8",
    )
    assert load_ocr_config(tmp_path) is None


def test_load_ignores_unknown_keys(tmp_path: Path) -> None:
    """Unknown keys silently dropped; the load returns the parsed
    state with declared fields populated. Operator WARNING covered
    by the dedicated test below."""
    path = ocr_config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "selected_detection_key": "stock",
                "selected_recognition_key": "stock",
                "hf_pinned_revision": None,
                "future_one": "a",
            }
        ),
        encoding="utf-8",
    )
    state = load_ocr_config(tmp_path)
    assert state is not None
    assert state.selected_detection_key == "stock"


# ── happy-path round trip ────────────────────────────────────────────────


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    """Standard cycle: save state → load it back → fields equal."""
    state = OCRConfigSidecar(
        selected_detection_key="huggingface",
        selected_recognition_key="huggingface",
        hf_pinned_revision="abcdef0",
    )
    save_ocr_config(tmp_path, state)
    loaded = load_ocr_config(tmp_path)
    assert loaded is not None
    assert loaded.selected_detection_key == "huggingface"
    assert loaded.selected_recognition_key == "huggingface"
    assert loaded.hf_pinned_revision == "abcdef0"
    assert loaded.schema_version == "1.0"


def test_save_creates_data_root_if_missing(tmp_path: Path) -> None:
    """Cold install: data root not yet on disk; the save mkdir's it."""
    fresh = tmp_path / "first-run-data-root"
    assert not fresh.exists()
    save_ocr_config(fresh, OCRConfigSidecar())
    assert fresh.exists()
    assert (fresh / OCR_CONFIG_FILENAME).exists()


def test_save_overwrites_existing_state(tmp_path: Path) -> None:
    """Two saves: the second wins; no append, no merge."""
    save_ocr_config(
        tmp_path,
        OCRConfigSidecar(selected_detection_key="stock", selected_recognition_key="stock"),
    )
    save_ocr_config(
        tmp_path,
        OCRConfigSidecar(
            selected_detection_key="huggingface",
            selected_recognition_key="huggingface",
            hf_pinned_revision="v2",
        ),
    )
    loaded = load_ocr_config(tmp_path)
    assert loaded is not None
    assert loaded.selected_detection_key == "huggingface"
    assert loaded.hf_pinned_revision == "v2"


# ── on-disk wire shape ───────────────────────────────────────────────────


def test_saved_json_matches_spec_shape(tmp_path: Path) -> None:
    """Dump the saved file; assert key set + types match spec §7a.
    M9.2 adds ``auto_rotate_on_load`` and ``auto_rotate_method``."""
    state = OCRConfigSidecar(
        selected_detection_key="stock",
        selected_recognition_key="stock",
        hf_pinned_revision="rev-pin",
    )
    save_ocr_config(tmp_path, state)
    on_disk = json.loads(ocr_config_path(tmp_path).read_text(encoding="utf-8"))
    assert set(on_disk.keys()) == {
        "schema_version",
        "selected_detection_key",
        "selected_recognition_key",
        "hf_pinned_revision",
        "auto_rotate_on_load",
        "auto_rotate_method",
    }
    assert on_disk["schema_version"] == "1.0"
    assert isinstance(on_disk["schema_version"], str)
    assert on_disk["selected_detection_key"] == "stock"
    assert on_disk["selected_recognition_key"] == "stock"
    assert on_disk["hf_pinned_revision"] == "rev-pin"
    assert on_disk["auto_rotate_on_load"] is True
    assert on_disk["auto_rotate_method"] == "auto"


def test_saved_json_serialises_null_revision(tmp_path: Path) -> None:
    """``hf_pinned_revision=None`` → JSON ``null`` (not ``"None"``)."""
    save_ocr_config(tmp_path, OCRConfigSidecar())
    on_disk = json.loads(ocr_config_path(tmp_path).read_text(encoding="utf-8"))
    assert on_disk["hf_pinned_revision"] is None


# ── atomicity invariants ─────────────────────────────────────────────────


def test_save_does_not_leave_tmp_file_on_success(tmp_path: Path) -> None:
    """``Path.replace`` consumes the tmp file; no stray ``.tmp`` afterwards."""
    save_ocr_config(tmp_path, OCRConfigSidecar())
    final = ocr_config_path(tmp_path)
    tmp_marker = final.with_suffix(final.suffix + ".tmp")
    assert final.exists()
    assert not tmp_marker.exists(), "stray .tmp left after save — atomic-rename broken"


# ── save-error policy (spec §7a: log-and-swallow, NOT re-raise) ──────────


def test_save_swallows_oserror_and_logs_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec §7a: save errors are logged-and-swallowed (NOT re-raised
    like ``session_state.save_session_state``). Rationale: a failed
    sidecar save must not turn a 200 OCR-config POST into a 500 — the
    in-process carrier is still authoritative for the live session.
    The WARNING uses the stable substring ``ocr_config_save_failed``
    so an operator can spot persistent disk-side failures.
    """

    def _boom(self, target):  # type: ignore[no-untyped-def]
        raise OSError("simulated rename failure")

    monkeypatch.setattr(Path, "replace", _boom)
    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.persistence.ocr_config"):
        # MUST NOT raise — that's the policy contract.
        save_ocr_config(tmp_path, OCRConfigSidecar())
    matching = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "ocr_config_save_failed" in r.getMessage()
    ]
    assert len(matching) == 1, (
        "Expected exactly one WARNING with stable substring "
        "'ocr_config_save_failed' — operator/CI grep contract."
    )


# ── extras-drift WARNING (spec §7a) ──────────────────────────────────────


def test_load_logs_warning_with_stable_substring_when_extras_dropped(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Spec §7a: load with unknown keys MUST emit a WARNING containing
    the stable grep-able substring ``ocr_config_extras_dropped``. This
    is the analogue of D-041's ``session_state_extras_dropped`` but
    scoped to forward-compat drift among SPA versions (the file is not
    legacy-shared, so cross-binary drift doesn't apply).

    The dropped key names also appear in ``extra=`` so structured-log
    parsers can route on them.
    """
    path = ocr_config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "selected_detection_key": "stock",
                "selected_recognition_key": "stock",
                "hf_pinned_revision": None,
                "future_one": "a",
                "future_two": "b",
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.persistence.ocr_config"):
        state = load_ocr_config(tmp_path)

    assert state is not None
    matching = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "ocr_config_extras_dropped" in r.getMessage()
    ]
    assert len(matching) == 1
    dropped = getattr(matching[0], "ocr_config_dropped_keys", None)
    assert dropped == ["future_one", "future_two"], (
        f"WARNING extra= must list dropped key names; got {dropped!r}"
    )


def test_load_does_not_warn_when_no_extras_present(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Negative pin: a normal load must NOT emit the WARNING. Otherwise
    every release would trip the drift alarm and the signal would be
    useless."""
    path = ocr_config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "selected_detection_key": "stock",
                "selected_recognition_key": "stock",
                "hf_pinned_revision": None,
            }
        ),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="pd_ocr_labeler_spa.core.persistence.ocr_config"):
        state = load_ocr_config(tmp_path)
    assert state is not None
    drift_warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "ocr_config_extras_dropped" in r.getMessage()
    ]
    assert drift_warnings == []
