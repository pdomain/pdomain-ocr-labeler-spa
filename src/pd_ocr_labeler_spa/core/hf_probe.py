"""Pure HF last-modified probe (slice 8c-iii-b).

Returns the published Hugging Face model's ``last_modified`` timestamp,
or ``None`` when ``huggingface_hub`` is unavailable, the network is
unreachable, or the repo has no ``last_modified`` metadata. **The
function logs failure but never raises** — its single caller is the
default-model selection algorithm (``model_selection.pick_default_keys``)
which treats a ``None`` HF probe as "HF unreachable" and prefers a
local pair when one exists. Surfacing exceptions here would convert a
benign offline state into a 5xx on every OCR-config snapshot.

Source of truth: legacy
``pd_ocr_labeler/operations/ocr/model_selection_operations.py``,
``ModelSelectionOperations.fetch_hf_last_modified`` (lines 169-205).

Slice scope: the network probe only. Discovery composition and the
``api/ocr_config._build_snapshot`` wiring (replacing the iter-10
hardcoded ``stock-fallback``) is slice 8c-iii-c.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


HF_DEFAULT_REPO = "CT2534/pd-ocr-models"
"""Default Hugging Face repository for OCR weights.

Mirrors legacy ``HF_DEFAULT_REPO``. The detection / recognition
filenames live there too but they're only needed at *download* time —
this probe only asks the hub when the repo's metadata last changed.
"""


def fetch_hf_last_modified(*, revision: str | None = None, timeout: float = 5.0) -> datetime | None:
    """Return the HF model's last-modified timestamp, or ``None``.

    Parameters
    ----------
    revision:
        Optional git revision (commit, tag, or branch). ``None`` (the
        default) resolves to the repo's ``main`` branch.
    timeout:
        HTTP timeout in seconds passed through to ``HfApi.model_info``.
        Default mirrors the legacy 5-second budget; selection-time
        callers may want a tighter budget so the OCR-config GET stays
        snappy when offline.

    Returns
    -------
    datetime | None
        Tz-aware UTC ``datetime`` on success; ``None`` on any failure
        path (missing dep, network error, repo metadata absent). Naive
        timestamps from older ``huggingface_hub`` versions are stamped
        UTC (matches legacy behaviour).

    Notes
    -----
    Errors are *never* propagated — the caller is selection-time code
    that must work offline. Operators wanting visibility get an INFO
    log line on probe failure (same severity as legacy).
    """
    try:
        from huggingface_hub import HfApi
    except ImportError:
        logger.debug("huggingface_hub not installed; skipping HF probe")
        return None

    try:
        info = HfApi().model_info(
            HF_DEFAULT_REPO,
            revision=revision,
            timeout=timeout,
        )
    except Exception as exc:
        logger.info(
            "HF probe failed for %s@%s: %s",
            HF_DEFAULT_REPO,
            revision or "main",
            exc,
        )
        return None

    last_modified = getattr(info, "last_modified", None)
    if last_modified is None:
        return None
    if isinstance(last_modified, datetime) and last_modified.tzinfo is None:
        # Older `huggingface_hub` returned naive UTC datetimes; legacy
        # promotes them rather than dropping the value on the floor.
        last_modified = last_modified.replace(tzinfo=UTC)
    return last_modified


__all__ = [
    "HF_DEFAULT_REPO",
    "fetch_hf_last_modified",
]
