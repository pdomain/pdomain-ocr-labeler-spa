"""Resolve the suite compute-device preference for OCR predictors.

Reads ``apps["pdomain-ocr-labeler-spa"].compute_device`` (falling back to
the suite-wide default, then auto-detection) via
``pdomain_ops.suite.device_prefs.resolve_effective_device``. Consumed by
both ``PredictorCache.get_or_create`` (request-time) and the CLI startup
banner (``__main__.main``), so this must never raise — any prefs-read
failure degrades to ``None`` (keep existing auto-detect behavior).

``resolve_effective_device`` can return ``"local"``: the CUDA
auto-detect sentinel from ``pdomain_ops.gpu.device.pick_device()``, not a
torch device string. That case (and unset/empty) means "no explicit
preference" here, so it maps to ``None`` rather than being passed to
``predictor.to("local")``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pdomain_ops.suite.device_prefs import resolve_effective_device
from pdomain_ops.suite.prefs import LocalFilePrefs

if TYPE_CHECKING:
    from pdomain_ops.suite.prefs import PrefsAdapter

logger = logging.getLogger(__name__)

_APP_ID = "pdomain-ocr-labeler-spa"
_AUTO_DETECT_SENTINEL = "local"


def resolve_ocr_device_override(prefs: PrefsAdapter | None = None) -> str | None:
    """Return the suite-persisted device override, or ``None`` to auto-detect."""
    try:
        effective = resolve_effective_device(prefs or LocalFilePrefs(), _APP_ID)
    except Exception:
        logger.exception("suite compute-device preference read failed; auto-detecting")
        return None
    if not effective or effective == _AUTO_DETECT_SENTINEL:
        return None
    return effective


__all__ = ["resolve_ocr_device_override"]
