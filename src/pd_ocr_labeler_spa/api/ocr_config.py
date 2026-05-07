"""``/api/ocr-config`` router — read + stateless-mutate (M3 slices 8a + 8c-i + 8c-iii-c).

Spec authority:

- ``specs/02-backend.md §5.8`` lines 317-322 — endpoint contracts.
- ``specs/01-data-models.md`` lines 374-400 — DTO shapes (defined in
  ``core/ocr_models.py`` per iter 7 / commit 9201caa).

What slice 8a shipped:

- ``GET /api/ocr-config`` returns a hardcoded "stock fallback" payload
  composed from the iter-7 DTOs.

What slice 8c-i added:

- ``POST /api/ocr-config/models`` validates the request keys against
  the same stock-only option lists and echoes a ``GetOCRConfigResponse``
  back. Selection is **not yet persisted** — that needs an
  ``OCRConfigCarrier`` + ``ocr_config.json`` writeback (slice 8c-iv+).

What slice 8c-iii-c adds (this slice):

- ``_build_snapshot`` no longer hardcodes ``selection_reason="stock-fallback"``.
  It now composes ``ModelOptionRecord`` from the discovery pipeline
  (``core.model_discovery.discover_local_pairs`` +
  ``core.hf_probe.fetch_hf_last_modified``) and runs
  ``core.model_selection.pick_default_keys`` to pick a real reason. In
  the empty-test world (no local pairs, ``huggingface_hub`` unavailable
  or unreachable) the picker still produces ``"stock-fallback"`` — so
  every slice-8a/-8c-i acceptance test stays green without new fixtures.
- The option lists themselves remain stock-only at this slice. Surfacing
  HF and local options into ``detection_options`` / ``recognition_options``
  is wired in slice 8c-iv+ when the carrier shape lands and selection
  is persisted; until then the picker's keys can diverge from the
  exposed options without violating the wire contract because the
  POST endpoint still only accepts ``"stock"`` keys.

What this router still deliberately does NOT do:

- ``POST /api/ocr-config/rescan`` — requires the carrier (slice 8c-iv+).
- Persist a selection. The mutation route is stateless; every call
  validates against the stock option lists and returns the echo-shaped
  response.
- Surface non-stock options. ``pick_default_keys`` may return
  ``("huggingface", "huggingface", "hf-latest")`` when probing succeeds,
  but the response option lists stay stock-only and ``selected_*`` stays
  ``"stock"`` — what changes is ``selection_reason``. The slice-8c-iii-c
  scope is to *replace* the hardcoded reason with a real one, not to
  reshape the option-list contract. (Doing both at once would require
  the carrier to round-trip selection through POST, which is deferred.)
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..core.hf_probe import HF_DEFAULT_REPO, fetch_hf_last_modified
from ..core.model_discovery import (
    LocalModelPair,
    discover_local_pairs,
    pairs_to_model_option_records,
)
from ..core.model_selection import HF_LATEST_KEY, ModelOptionRecord, pick_default_keys
from ..core.ocr_config_state import OCRConfigCarrier
from ..core.ocr_models import GetOCRConfigResponse, OCRModelOption, SetOCRModelsRequest
from ..core.persistence.ocr_config import OCRConfigSidecar, save_ocr_config
from ..settings import Settings
from .dependencies import get_ocr_config_carrier, get_settings

router = APIRouter(prefix="/api/ocr-config", tags=["ocr-config"])

MODEL_STORE_DIRNAME = "pd-ml-models"
"""Trainer-managed weights directory name. Mirror of legacy
``ModelSelectionOperations.MODEL_STORE_DIRNAME`` (legacy
``pd_ocr_labeler/operations/ocr/model_selection_operations.py`` line 63).
The full path is ``<os-data-home>/pd-ml-models`` per
``_resolve_local_models_root`` below."""


# Slice 8a stock options. Hoisted to module level so they're built once
# rather than per-request. ``OCRModelOption`` is a frozen pydantic model
# (``extra="forbid"``); sharing instances across requests is safe.
_STOCK_DETECTION = OCRModelOption(
    key="stock",
    label="Stock (bundled DocTR)",
    source="stock",
    is_default=True,
)

_STOCK_RECOGNITION = OCRModelOption(
    key="stock",
    label="Stock (bundled DocTR)",
    source="stock",
    is_default=True,
)


def _resolve_local_models_root() -> Path:
    """Return the OS-aware root where ``pd-ocr-trainer`` stores fine-tuned
    weights. Mirror of legacy ``get_shared_models_root`` (legacy
    ``pd_ocr_labeler/operations/ocr/model_selection_operations.py`` lines
    127-146).

    Tests override this by monkeypatching the module-level callable so
    discovery walks a tmp_path tree instead of the host-wide trainer
    directory. (A Settings field is the intended seam once the
    ``OCRConfigCarrier`` lands in slice 8c-iv+; pinning a module-level
    helper today keeps the slice scope to "wire the picker" without
    reshaping ``Settings``.)
    """
    system_name = platform.system()
    if system_name == "Linux":
        data_home = os.getenv("XDG_DATA_HOME")
        base_dir = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    elif system_name == "Darwin":
        base_dir = Path.home() / "Library" / "Application Support"
    elif system_name == "Windows":
        appdata = os.getenv("APPDATA")
        base_dir = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        base_dir = Path.home() / ".local" / "share"
    return base_dir / MODEL_STORE_DIRNAME


def _gather_pairs_and_records() -> tuple[list[LocalModelPair], list[ModelOptionRecord]]:
    """Discovery-pipeline output kept as a paired result so the router
    can build option lists (which need the local pair's ``profile`` /
    ``signature`` for the legacy-style label) AND the picker's record
    list (which only needs the abstract triple) without walking twice.
    """
    hf_record = ModelOptionRecord(
        key=HF_LATEST_KEY,
        source="huggingface",
        hf_last_modified=fetch_hf_last_modified(),
        local_mtime=None,
        has_detection=True,
        has_recognition=True,
        is_preferred_profile=False,
    )
    local_pairs = discover_local_pairs(_resolve_local_models_root())
    local_records = pairs_to_model_option_records(local_pairs)
    return local_pairs, [hf_record, *local_records]


def _gather_records() -> list[ModelOptionRecord]:
    """Build the ``ModelOptionRecord`` list fed to ``pick_default_keys``.

    Composes:
      * One ``source="huggingface"`` record (always present so the picker
        can decide between ``hf-latest`` / ``hf-unreachable-no-local`` /
        etc.); ``hf_last_modified`` is ``None`` when the probe fails for
        any reason — see ``core.hf_probe`` contract: never raises.
      * Zero or more ``source="local"`` records, one per discovered pair.
        An unreadable / missing models root yields zero local records
        (``discover_local_pairs`` returns ``[]``).
    """
    hf_record = ModelOptionRecord(
        key=HF_LATEST_KEY,
        source="huggingface",
        hf_last_modified=fetch_hf_last_modified(),
        local_mtime=None,
        has_detection=True,
        has_recognition=True,
        is_preferred_profile=False,
    )
    local_pairs = discover_local_pairs(_resolve_local_models_root())
    local_records = pairs_to_model_option_records(local_pairs)
    return [hf_record, *local_records]


def _build_option_lists(
    local_pairs: list[LocalModelPair],
    *,
    selected_detection: str,
    selected_recognition: str,
) -> tuple[list[OCRModelOption], list[OCRModelOption]]:
    """Build the wire-shaped detection / recognition option lists.

    Slice 8c-v-a: surfaces stock + HF (always) + one entry per local
    pair. Labels mirror legacy
    ``pd_ocr_labeler/operations/ocr/model_selection_operations.py``:

    - HF: ``f"Hugging Face: {HF_DEFAULT_REPO} (latest)"`` (legacy line 353).
    - Local: ``f"{profile}: {signature}"`` (legacy line 288).

    ``is_default=True`` is set on whichever option matches the currently
    selected key — this lets the modal render the selection without
    diffing keys client-side. (For now both detection and recognition
    use the same option-list shape; if a divergent shape ever surfaces,
    each list could be built independently — but legacy uses identical
    catalogs, so we replicate that.)
    """
    hf_label = f"Hugging Face: {HF_DEFAULT_REPO} (latest)"
    hf_option_det = OCRModelOption(
        key=HF_LATEST_KEY,
        label=hf_label,
        source="huggingface",
        is_default=(selected_detection == HF_LATEST_KEY),
    )
    hf_option_reco = OCRModelOption(
        key=HF_LATEST_KEY,
        label=hf_label,
        source="huggingface",
        is_default=(selected_recognition == HF_LATEST_KEY),
    )

    detection_options: list[OCRModelOption] = [
        OCRModelOption(
            key=_STOCK_DETECTION.key,
            label=_STOCK_DETECTION.label,
            source=_STOCK_DETECTION.source,
            is_default=(selected_detection == _STOCK_DETECTION.key),
        ),
        hf_option_det,
    ]
    recognition_options: list[OCRModelOption] = [
        OCRModelOption(
            key=_STOCK_RECOGNITION.key,
            label=_STOCK_RECOGNITION.label,
            source=_STOCK_RECOGNITION.source,
            is_default=(selected_recognition == _STOCK_RECOGNITION.key),
        ),
        hf_option_reco,
    ]

    for pair in local_pairs:
        local_label = f"{pair.profile}: {pair.signature}"
        detection_options.append(
            OCRModelOption(
                key=pair.key,
                label=local_label,
                source="local",
                is_default=(selected_detection == pair.key),
            )
        )
        recognition_options.append(
            OCRModelOption(
                key=pair.key,
                label=local_label,
                source="local",
                is_default=(selected_recognition == pair.key),
            )
        )

    return detection_options, recognition_options


def _build_snapshot(
    selected_detection: str,
    selected_recognition: str,
    hf_pinned_revision: str | None,
) -> GetOCRConfigResponse:
    """Compose a ``GetOCRConfigResponse`` from the surfaced option lists +
    a real ``selection_reason`` derived from the discovery pipeline.

    Slice 8c-v-a: option lists now include stock + HF (always) + zero-or-
    more local pairs. The caller's ``selected_*`` keys must be present
    in the corresponding option list (the route-level POST validation
    enforces this); selection is never silently rewritten here.

    Slice 8c-iii-c's ``selection_reason`` contract still applies — the
    picker's reason is honest about what *would* be the default; the
    user's actual selection (``selected_*``) is sourced from the carrier.
    """
    local_pairs, records = _gather_pairs_and_records()
    _, _, reason = pick_default_keys(records)
    detection_options, recognition_options = _build_option_lists(
        local_pairs,
        selected_detection=selected_detection,
        selected_recognition=selected_recognition,
    )
    return GetOCRConfigResponse(
        detection_options=detection_options,
        recognition_options=recognition_options,
        selected_detection=selected_detection,
        selected_recognition=selected_recognition,
        hf_pinned_revision=hf_pinned_revision,
        selection_reason=reason,
    )


@router.get("", response_model=GetOCRConfigResponse)
def get_ocr_config(
    carrier: OCRConfigCarrier = Depends(get_ocr_config_carrier),
) -> GetOCRConfigResponse:
    """Return an OCR-config snapshot.

    Spec §02-backend.md §5.8 line 319. The response body composes the
    iter-7 DTOs; ``selection_reason`` is computed from the slice-8c-iii
    discovery pipeline (HF probe + local-models walk +
    ``pick_default_keys``). Option lists remain stock-only — surfacing
    HF / local options is slice 8c-iv-b+ work.

    Slice 8c-iv-a wires the ``OCRConfigCarrier``: the GET reads the
    *currently selected* triple from the carrier (defaults to
    ``("stock", "stock", None)`` until a POST mutates it), and a
    subsequent GET reflects the POST's selection within the same
    process. Disk-side persistence is slice 8c-iv-b.
    """
    detection, recognition, revision = carrier.snapshot()
    return _build_snapshot(
        selected_detection=detection,
        selected_recognition=recognition,
        hf_pinned_revision=revision,
    )


@router.post("/models", response_model=GetOCRConfigResponse)
def post_ocr_config_models(
    req: SetOCRModelsRequest,
    carrier: OCRConfigCarrier = Depends(get_ocr_config_carrier),
    settings: Settings = Depends(get_settings),
) -> GetOCRConfigResponse:
    """Validate + persist OCR model selection.

    Spec §02-backend.md §5.8 line 320. The route shape is canonical;
    selection persists in two layers:

    - **In-process** (slice 8c-iv-a): ``OCRConfigCarrier`` so a
      subsequent ``GET /api/ocr-config`` in the same process reflects
      the change.
    - **On-disk** (slice 8c-iv-b, this slice): ``ocr_config.json``
      sidecar at ``<data_root>/ocr_config.json`` so the selection
      survives a restart. The save runs **after** ``set_models``
      reports an actual state change — idempotent re-POSTs of the
      same triple skip the disk I/O.

    Save errors are logged-and-swallowed inside ``save_ocr_config``
    (spec §7a) so a sidecar-write failure cannot turn a 200 OCR-config
    POST into a 500. The user's selection still takes effect for the
    live session; the operator sees the failure via the stable
    WARNING substring ``ocr_config_save_failed``.

    Unknown keys → 400. The wire body's ``selection_reason`` is the
    slice-8c-iii-c picker output.
    """
    # Slice 8c-v-a: validate against the *currently surfaced* option
    # lists, not just stock. The discovery pipeline is the single source
    # of truth for legitimate keys; gating POST against the same set of
    # records `_build_snapshot` would surface keeps the GET/POST contract
    # in sync (e.g. a key that wouldn't appear in a subsequent GET can't
    # be POSTed). HF key + every discovered local pair key are accepted.
    local_pairs, _ = _gather_pairs_and_records()
    detection_options, recognition_options = _build_option_lists(
        local_pairs,
        selected_detection=req.detection_key,
        selected_recognition=req.recognition_key,
    )
    detection_keys = {opt.key for opt in detection_options}
    recognition_keys = {opt.key for opt in recognition_options}
    if req.detection_key not in detection_keys:
        raise HTTPException(
            status_code=400,
            detail=f"unknown detection_key: {req.detection_key!r}",
        )
    if req.recognition_key not in recognition_keys:
        raise HTTPException(
            status_code=400,
            detail=f"unknown recognition_key: {req.recognition_key!r}",
        )
    changed = carrier.set_models(
        detection_key=req.detection_key,
        recognition_key=req.recognition_key,
        hf_pinned_revision=req.hf_pinned_revision,
    )
    # Slice 8c-iv-b: persist to disk on real state change. Idempotent
    # re-POSTs are no-ops (carrier reports unchanged → skip the I/O).
    # The sidecar shape mirrors the wire DTO field names exactly so a
    # future contributor can map persisted → response without aliasing.
    if changed:
        save_ocr_config(
            settings.data_root,
            OCRConfigSidecar(
                selected_detection_key=req.detection_key,
                selected_recognition_key=req.recognition_key,
                hf_pinned_revision=req.hf_pinned_revision,
            ),
        )
    return _build_snapshot(
        selected_detection=req.detection_key,
        selected_recognition=req.recognition_key,
        hf_pinned_revision=req.hf_pinned_revision,
    )


def install_ocr_config_router(app) -> None:  # type: ignore[no-untyped-def]
    """Register the OCR config router. Called from ``bootstrap.build_app``."""
    app.include_router(router)


__all__ = [
    "MODEL_STORE_DIRNAME",
    "install_ocr_config_router",
    "router",
]
