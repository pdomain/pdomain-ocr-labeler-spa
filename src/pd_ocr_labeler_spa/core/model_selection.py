"""Pure OCR-model selection algorithm — port of legacy ``pick_default_keys``.

Source of truth: legacy
``pd_ocr_labeler/operations/ocr/model_selection_operations.py``
``ModelSelectionOperations.pick_default_keys`` plus its helpers
``_candidate_keys_for_component`` / ``_latest_key`` /
``_is_preferred_profile_key`` / ``latest_local_mtime``.

Slice 8c-ii intentionally lands ONLY the pure decision function. The
discovery side (HF probe, local-models walk, mtime collection) is
adapter-shaped work and slips to slice 8c-iii+. Wiring this into
``api/ocr_config._build_snapshot`` (so ``selection_reason`` stops
being a hardcoded ``stock-fallback``) is slice 8c-iii's job, not this
slice's.

Algorithm precedence (verbatim from legacy lines 432-483):

1. HF latest if reachable AND (no local OR HF >= newest local mtime)
   → reason ``hf-latest``.
2a. Local strictly newer than HF, both options viable for the
    requested component → ``local-newer-than-hf``.
2b. HF unreachable but local pair available → ``local-only-hf-unreachable``.
3. HF reachable but no local pair (only triggers when local mtime
   exists from incomplete records but no complete pair) →
   ``hf-only``.
4. HF record present but unreachable, no local → ``hf-unreachable-no-local``
   (returns the stock key as the picked pair so the caller can boot).
5. Bare fallback → ``stock-fallback``.

The detection and recognition keys can diverge in case 2 — local
discovery may yield det-only or reco-only entries. Legacy returns
whichever local key it found *per component*.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pd_ocr_labeler_spa.core.ocr_models import GetOCRConfigResponse

HF_LATEST_KEY = "huggingface"
"""Key for the published HF repo at ``main`` — legacy line 61."""

STOCK_KEY = "stock"
"""Key for the bundled DocTR weights fallback.

Note legacy uses ``"default"`` (line 59) but the SPA-side
``OCRModelOption`` (``core/ocr_models.py``) uses ``"stock"`` for the
``source="stock"`` discriminant. This module aligns with the SPA
shape — the wire contract has ``selected_detection: "stock"``.
"""

_TIMESTAMP_SUFFIX = re.compile(r"(\d{10})$")
"""Trailing 10-digit unix-ish timestamp inside a local-model
signature, e.g. ``all/base-ocr-1700000000`` — legacy line 65.
"""

_PREFERRED_PROFILES = {"all", "base-ocr"}
"""Profile-prefix shortlist the legacy picker honors — line 64."""

SelectionReason = Literal[
    "hf-latest",
    "hf-only",
    "local-newer-than-hf",
    "local-only-hf-unreachable",
    "hf-unreachable-no-local",
    "stock-fallback",
]
"""Mirror of ``GetOCRConfigResponse.selection_reason``.

Pinned via runtime assertion below to catch drift between the
algorithm and the wire DTO.
"""

# Defensive sync check — if the DTO Literal evolves the algorithm
# must follow. ``__args__`` on Literal returns the value tuple.
_DTO_REASONS = set(GetOCRConfigResponse.model_fields["selection_reason"].annotation.__args__)
_LOCAL_REASONS = {
    "hf-latest",
    "hf-only",
    "local-newer-than-hf",
    "local-only-hf-unreachable",
    "hf-unreachable-no-local",
    "stock-fallback",
}
assert _DTO_REASONS == _LOCAL_REASONS, (
    "selection_reason drift between core.ocr_models.GetOCRConfigResponse "
    "and core.model_selection — keep them in sync."
)


@dataclass(frozen=True)
class ModelOptionRecord:
    """Internal record fed to ``pick_default_keys``.

    Discovery (slice 8c-iii+) builds these from HF probes and local
    ``.pt`` walks; ``pick_default_keys`` is pure over them. Kept
    separate from the wire-side ``OCRModelOption`` so we can carry
    fields the wire DTO doesn't expose (``hf_last_modified``,
    ``local_mtime``, ``is_preferred_profile``).
    """

    key: str
    source: Literal["stock", "huggingface", "local"]
    hf_last_modified: datetime | None
    local_mtime: datetime | None
    has_detection: bool
    has_recognition: bool
    is_preferred_profile: bool

    def __post_init__(self) -> None:
        if self.source == "local" and self.local_mtime is None:
            raise ValueError(f"local ModelOptionRecord {self.key!r} requires local_mtime")
        if self.source == "huggingface" and self.local_mtime is not None:
            raise ValueError(f"huggingface ModelOptionRecord {self.key!r} must not carry local_mtime")

    @property
    def hf_reachable(self) -> bool:
        """An HF record is *reachable* when its ``last_modified`` is set.

        Mirrors legacy line 455 — ``hf_available`` is the truthy check
        on ``hf_last_modified``.
        """
        return self.source == "huggingface" and self.hf_last_modified is not None


def _is_preferred_profile_key(key: str) -> bool:
    """Legacy lines 72-74 — first segment before ``/`` matched
    case-insensitively against ``_PREFERRED_PROFILES``.
    """
    profile_name = key.split("/", 1)[0].strip().lower()
    return profile_name in _PREFERRED_PROFILES


def _latest_key(keys: list[str]) -> str | None:
    """Legacy lines 76-87 — latest by trailing-10-digit timestamp.

    Keys without a trailing timestamp sort below those with one;
    string sort breaks ties.
    """
    if not keys:
        return None

    def sort_key(key: str) -> tuple[int, str, str]:
        signature = key.split("/", 1)[1] if "/" in key else key
        match = _TIMESTAMP_SUFFIX.search(signature)
        timestamp = match.group(1) if match else ""
        return (1 if match else 0, timestamp, key)

    return max(keys, key=sort_key)


def _candidate_keys_for_component(
    records: list[ModelOptionRecord],
    component: Literal["detection", "recognition"],
) -> list[str]:
    """Legacy lines 89-115 — per-component filter + preferred-subset."""
    if component == "detection":
        keys = [r.key for r in records if r.source == "local" and r.has_detection]
    else:
        keys = [r.key for r in records if r.source == "local" and r.has_recognition]

    preferred = [k for k in keys if _is_preferred_profile_key(k)]
    return preferred or keys


def _latest_local_mtime(records: Iterable[ModelOptionRecord]) -> datetime | None:
    """Legacy lines 306-327 — newest mtime across all local records.

    Iterates regardless of pair completeness, matching legacy's
    behavior of looping the det/reco paths individually.
    """
    latest: datetime | None = None
    for r in records:
        if r.source != "local" or r.local_mtime is None:
            continue
        if latest is None or r.local_mtime > latest:
            latest = r.local_mtime
    return latest


def pick_default_keys(
    records: list[ModelOptionRecord],
) -> tuple[str, str, SelectionReason]:
    """Return ``(detection_key, recognition_key, reason)``.

    Caller-facing contract — see module docstring for precedence.
    Never raises; an empty/degenerate ``records`` falls through to
    ``stock-fallback`` so the GET endpoint never 500s.
    """
    hf_record = next((r for r in records if r.source == "huggingface"), None)
    hf_reachable = hf_record is not None and hf_record.hf_reachable

    latest_local_det = _latest_key(_candidate_keys_for_component(records, "detection"))
    latest_local_reco = _latest_key(_candidate_keys_for_component(records, "recognition"))
    local_mtime = _latest_local_mtime(records)

    # Case 1: HF reachable, AND (no local OR HF >= local newest).
    if hf_reachable:
        assert hf_record is not None  # for type-checkers
        assert hf_record.hf_last_modified is not None
        if local_mtime is None or hf_record.hf_last_modified >= local_mtime:
            return HF_LATEST_KEY, HF_LATEST_KEY, "hf-latest"

    # Case 2: local pair available (per component).
    if latest_local_det is not None and latest_local_reco is not None:
        reason: SelectionReason = "local-newer-than-hf" if hf_reachable else "local-only-hf-unreachable"
        return latest_local_det, latest_local_reco, reason

    # Case 4: HF record present but unreachable, no local pair.
    if hf_record is not None and not hf_reachable:
        return STOCK_KEY, STOCK_KEY, "hf-unreachable-no-local"

    # Case 3: HF reachable but no local pair (legacy line 480-481).
    if hf_reachable:
        return HF_LATEST_KEY, HF_LATEST_KEY, "hf-only"

    # Case 5: bare fallback.
    return STOCK_KEY, STOCK_KEY, "stock-fallback"
