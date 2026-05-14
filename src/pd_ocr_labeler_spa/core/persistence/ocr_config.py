"""Read/write of ``<data_root>/ocr_config.json`` — SPA-only sidecar for
``OCRConfigCarrier`` (M3 slice 8c-iv-b).

Spec: ``specs/09-persistence.md §7a`` + ``specs/01-data-models.md`` (the
``ocr_config.json`` cross-ref).

This is the disk half of the in-process ``OCRConfigCarrier`` (slice
8c-iv-a). The carrier holds the user's currently-selected OCR
detection / recognition keys + ``hf_pinned_revision``; this module
makes that selection survive a server restart.

Schema (verbatim from spec §7a)::

    {"schema_version": "1.0",
     "selected_detection_key": "stock",
     "selected_recognition_key": "stock",
     "hf_pinned_revision": null}

Field-name parity with the wire DTOs is **mandatory** —
``selected_detection_key`` / ``selected_recognition_key`` /
``hf_pinned_revision`` are exactly the keys ``SetOCRModelsRequest`` and
``GetOCRConfigResponse`` carry, so a future contributor can map the
sidecar directly into a route response without an aliasing layer.

**Not legacy-shared.** Unlike ``session_state.json`` (D-003), the
legacy ``pd-ocr-labeler`` binary does NOT read or write this file.
That has two implications: ``schema_version`` parity is purely
intra-SPA (future-version forward-compat), and ``extras-tolerance``
exists for future SPA additive fields, not cross-binary drift.

**Save-error policy diverges from session_state.** Spec §7a:
``save_ocr_config`` logs-and-swallows OSError (with stable WARNING
substring ``ocr_config_save_failed``); it does NOT re-raise. Rationale:
a failed sidecar save must not turn a 200 OCR-config POST into a 500.
The in-process carrier is the authoritative source-of-truth for the
live session; the sidecar is "best-effort persistence across restart".
Persistent disk-side failure (e.g. read-only data root, full disk)
shows up in operator logs via the stable substring.

**Load failure modes (all return None):**

- File missing (cold start).
- File present but unparsable as JSON.
- JSON not an object (e.g. list at the top level).
- Object fails Pydantic validation (e.g. integer where string expected).

The caller (``build_app`` lifespan hook) treats ``None`` as "no prior
selection persisted; seed the carrier with defaults".

**Atomicity:** ``tmp + replace`` mirrors ``session_state.save_session_state``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pd_ocr_labeler_spa.core.ocr_config_state import AutoRotateMethod
from pd_ocr_labeler_spa.core.persistence.paths import ocr_config_path

logger = logging.getLogger(__name__)

OCR_CONFIG_FILENAME = "ocr_config.json"
"""Re-exported from ``paths`` for callers that only import this module."""

OCR_CONFIG_SCHEMA_VERSION = "1.0"
"""Spec §7a: schema_version is the **string** ``"1.0"`` (parity with
``session_state.json``), not an int."""


class OCRConfigSidecar(BaseModel):
    """Persisted OCR model selection — restored on next startup.

    Field names mirror the wire DTOs in ``core/ocr_models.py`` so a
    future contributor can map sidecar → route-response without an
    aliasing layer.

    Defaults match ``OCRConfigCarrier()`` (slice 8c-iv-a):
    ``("stock", "stock", None)``. A cold-start save (no prior
    selection) is therefore a no-op in semantic terms — the on-disk
    bytes match a fresh-process carrier.
    """

    # Spec §7a: ``extra="ignore"`` — forward-compat with future SPA
    # versions adding additive fields. NOT cross-binary (legacy doesn't
    # touch this file). ``load_ocr_config`` separately logs dropped keys
    # at WARNING with substring ``ocr_config_extras_dropped`` so an
    # operator / CI grep can spot drift.
    model_config = ConfigDict(extra="ignore")

    schema_version: str = Field(
        default=OCR_CONFIG_SCHEMA_VERSION,
        description="Schema version string. Spec §7a fixes this at '1.0'.",
    )
    selected_detection_key: str = Field(
        default="stock",
        description=(
            "Detection model key. Mirrors ``GetOCRConfigResponse.selected_detection`` "
            "and ``SetOCRModelsRequest.detection_key``."
        ),
    )
    selected_recognition_key: str = Field(
        default="stock",
        description=(
            "Recognition model key. Mirrors ``GetOCRConfigResponse.selected_recognition`` "
            "and ``SetOCRModelsRequest.recognition_key``."
        ),
    )
    hf_pinned_revision: str | None = Field(
        default=None,
        description=(
            "Optional HF Hub revision pin (commit / tag). Mirrors "
            "``GetOCRConfigResponse.hf_pinned_revision``."
        ),
    )
    auto_rotate_on_load: bool = Field(
        default=True,
        description=(
            "When True, auto-rotate pass runs on project load. "
            "Mirrors ``GetOCRConfigResponse.auto_rotate_on_load``."
        ),
    )
    auto_rotate_method: AutoRotateMethod = Field(
        default="auto",
        description=(
            "Auto-rotate algorithm: 'gt-best-match' (uses GT text), "
            "'layout' (no GT required), or 'auto' (picks best available). "
            "Mirrors ``GetOCRConfigResponse.auto_rotate_method``."
        ),
    )


def load_ocr_config(data_root: Path) -> OCRConfigSidecar | None:
    """Read ``<data_root>/ocr_config.json`` if present and valid.

    Returns ``None`` (not an exception) on:

    - file missing
    - file unparsable as JSON
    - JSON not an object
    - object fails Pydantic validation

    All four are normal cold-start / drift conditions; the caller
    seeds ``OCRConfigCarrier`` with defaults when the load returns
    ``None``. Logged at ``debug`` level — a missing or stale file is
    the **expected** state on first run.

    When the load succeeds but the JSON contains keys not declared on
    ``OCRConfigSidecar``, those keys are silently dropped at the
    Pydantic layer (``extra="ignore"``); a separate WARNING with the
    stable substring ``ocr_config_extras_dropped`` lets an operator /
    CI grep spot uncoordinated SPA-version drift.
    """
    path = ocr_config_path(data_root)
    if not path.exists():
        logger.debug("No ocr_config sidecar at %s (cold start).", path)
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        logger.debug("Failed to read %s.", path, exc_info=True)
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("ocr_config sidecar at %s is not valid JSON; ignoring.", path, exc_info=True)
        return None
    if not isinstance(data, dict):
        logger.debug("ocr_config sidecar at %s is not a JSON object; ignoring.", path)
        return None
    try:
        parsed = OCRConfigSidecar.model_validate(data)
    except Exception:
        logger.debug("ocr_config sidecar at %s failed validation; ignoring.", path, exc_info=True)
        return None

    # Forward-compat drift detection — analogue of D-041's session_state pattern.
    declared = set(OCRConfigSidecar.model_fields.keys())
    raw_keys = set(data.keys())
    dropped = sorted(raw_keys - declared)
    if dropped:
        logger.warning(
            "ocr_config_extras_dropped — unknown key(s) %s in %s ignored "
            "(possible SPA-version forward-compat drift; stable substring for grep / CI gates).",
            dropped,
            path,
            extra={
                "ocr_config_dropped_keys": dropped,
                "ocr_config_path": str(path),
            },
        )
    return parsed


def save_ocr_config(data_root: Path, state: OCRConfigSidecar) -> None:
    """Write ``state`` atomically to ``<data_root>/ocr_config.json``.

    Atomicity: ``<path>.tmp`` then ``Path.replace`` — POSIX rename is
    atomic so readers see either the old file or the new file (never
    a half-written one).

    Creates ``data_root`` (and any parent dirs) if missing.

    **Save-error policy (spec §7a — diverges from
    ``session_state.save_session_state``):** any error during the
    write+replace is logged at WARNING with the stable substring
    ``ocr_config_save_failed`` and **swallowed**, NOT re-raised.
    Rationale: a failed sidecar save must not turn a 200 OCR-config
    POST into a 500. The in-process carrier is still authoritative for
    the live session; the user's selection takes effect immediately.
    Persistent disk-side failures (read-only data root, full disk)
    show up via the stable substring without crashing the request.
    """
    path = ocr_config_path(data_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state.model_dump(), indent=2, ensure_ascii=False)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning(
            "ocr_config_save_failed — could not persist OCR config to %s (%s). "
            "In-process carrier is still authoritative; selection took effect "
            "but will not survive restart. Stable substring for grep / CI gates.",
            path,
            exc,
            extra={
                "ocr_config_path": str(path),
                "ocr_config_save_error": repr(exc),
            },
        )
        return
    logger.debug(
        "Saved ocr_config sidecar to %s (det=%s reco=%s rev=%s).",
        path,
        state.selected_detection_key,
        state.selected_recognition_key,
        state.hf_pinned_revision,
    )


__all__ = [
    "OCR_CONFIG_FILENAME",
    "OCR_CONFIG_SCHEMA_VERSION",
    "OCRConfigSidecar",
    "load_ocr_config",
    "save_ocr_config",
]
