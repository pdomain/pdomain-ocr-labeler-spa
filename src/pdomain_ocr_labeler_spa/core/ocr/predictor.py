"""Keyed DocTR predictor cache.

Spec: ``docs/architecture/02-backend.md §1`` line 62
(``core/ocr/predictor.py — _get_or_create_predictor + cache``) and
``docs/architecture/02-backend.md §7`` (``local_doctr.py wraps ... a predictor
cache``).

Legacy reference: ``pd-ocr-labeler/pd_ocr_labeler/operations/ocr/
page_operations.py:270-304`` (``_get_or_create_predictor`` — lazy
build, fall through to stock when no HF/local weights resolved).

Design:

- The cache is **keyed** by ``(detection_key, recognition_key,
  hf_revision)`` so swapping models (e.g. via the OCR-config modal)
  doesn't require evicting the whole map. Legacy used a single mutable
  ``_docTR_predictor`` slot; the SPA model lets multiple predictors
  coexist (rare, but cheap) and makes "switch back to a previous
  selection" a cache hit.
- The cache itself is **I/O-free**: it never walks ``<data_root>/
  pdomain-ml-models``, never calls ``huggingface_hub``. Resolution of
  detection/recognition file paths is delegated to a
  ``WeightsResolver`` callable (slice will land in the
  ``LocalDoctrPageLoader`` wiring step). The default resolver returns
  ``None`` so any unknown key falls through to the stock factory —
  this matches legacy behavior when no HF descriptor is registered.
- Build failures (finetuned factory returning ``None``) raise
  ``PredictorBuildError`` rather than silently falling back to stock,
  so a misconfigured HF revision surfaces loudly in the OCR-config
  modal instead of pretending the user got what they asked for.

Thread safety: ``threading.Lock`` around the dict. Predictor build
itself is the slow path (model download / weights load); holding the
lock during build serialises duplicate concurrent builds for the same
key, matching legacy behaviour where ``_get_or_create_predictor`` is
called from a single PageOperations instance.
"""

from __future__ import annotations

import importlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PredictorKey:
    """Cache key for a built predictor.

    ``hf_revision`` is part of the key so pinning a different revision
    (re-using ``detection_key``/``recognition_key``) is a cache miss
    that triggers a fresh build.
    """

    detection_key: str
    recognition_key: str
    hf_revision: str | None


@dataclass(frozen=True)
class ResolvedWeights:
    """File paths the finetuned predictor factory needs.

    Returned by a ``WeightsResolver``. ``recognition_vocab`` is the
    text vocab (legacy ``page_operations.py:267`` stores this in
    ``self._recognition_vocab``); empty string when the recognition
    weights ship with their own vocab.
    """

    detection_path: str
    recognition_path: str
    recognition_vocab: str


WeightsResolver = Callable[[str, str, str | None], ResolvedWeights | None]
"""Pure callable: ``(detection_key, recognition_key, hf_revision) -> ResolvedWeights | None``.

``None`` means "no fine-tuned weights available — use stock". The
default resolver (see ``_default_resolver``) always returns ``None``;
real wiring (HF download + local-pair lookup) lands in a later slice
and is injected via constructor kwarg.
"""


class PredictorBuildError(RuntimeError):
    """The finetuned predictor factory returned ``None`` / failed to load.

    Legacy parity: ``page_operations.py:294-295`` raised
    ``RuntimeError("Failed to load fine-tuned DocTR weights")``. Same
    failure shape, named subclass for grep-ability.
    """


def _default_resolver(
    detection_key: str, recognition_key: str, hf_revision: str | None
) -> ResolvedWeights | None:
    """Stock-only default — every key resolves to "no finetuned weights"."""
    return None


class PredictorCache:
    """Keyed DocTR predictor cache.

    Use ``get_or_create(detection_key, recognition_key, hf_revision)``
    to either return a previously-built predictor or build + cache a
    fresh one. Predictors are opaque (``Any``) at this layer — they're
    consumed by ``Document.from_image_ocr_via_doctr(predictor=...)``
    which accepts whatever ``pdomain_book_tools.ocr.doctr_support``
    produces.

    ``device_resolver`` (optional) is called after every resolution —
    cache hit or fresh build — and, if it returns a device string, that
    device is applied via ``predictor.to(device)``. This is the uniform
    seam: ``get_default_doctr_predictor`` has no ``device=`` factory
    kwarg, so ``.to()`` is the only way to move an already-built
    predictor.
    """

    def __init__(
        self,
        *,
        weights_resolver: WeightsResolver | None = None,
        device_resolver: Callable[[], str | None] | None = None,
    ) -> None:
        self._cache: dict[PredictorKey, Any] = {}
        self._lock = threading.Lock()
        self._weights_resolver: WeightsResolver = weights_resolver or _default_resolver
        self._device_resolver = device_resolver

    def get_or_create(
        self,
        detection_key: str,
        recognition_key: str,
        hf_revision: str | None,
    ) -> Any:
        key = PredictorKey(
            detection_key=detection_key,
            recognition_key=recognition_key,
            hf_revision=hf_revision,
        )
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                predictor = cached
            else:
                predictor = self._build(key)
                self._cache[key] = predictor
        return self._apply_device_override(predictor)

    def _apply_device_override(self, predictor: Any) -> Any:
        if self._device_resolver is None:
            return predictor
        device = self._device_resolver()
        if not device:
            return predictor
        try:
            return predictor.to(device)
        except Exception:
            logger.exception("predictor.to(%r) failed; using predictor unchanged", device)
            return predictor

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def _build(self, key: PredictorKey) -> Any:
        """Build a new predictor for ``key``.

        Lazy import of ``pdomain_book_tools.ocr.doctr_support`` so the
        module is only loaded when an actual OCR run is requested —
        keeps test collection fast and avoids pulling torch into
        ``pytest --collect-only`` runs.
        """
        doctr_support = importlib.import_module("pdomain_book_tools.ocr.doctr_support")

        # Stock fast-path: both keys are the literal string "stock"
        # (the GET /api/ocr-config DTO contract — see
        # docs/architecture/01-data-models.md §OCRModelOption). No resolver call
        # needed.
        if key.detection_key == "stock" and key.recognition_key == "stock":
            return doctr_support.get_default_doctr_predictor()

        weights = self._weights_resolver(key.detection_key, key.recognition_key, key.hf_revision)
        if weights is None:
            # Resolver couldn't find weights → stock fallback. Matches
            # legacy ``page_operations.py:297-302``.
            logger.info(
                "predictor_resolver_returned_none — falling back to stock "
                "(detection=%s, recognition=%s, hf_revision=%s)",
                key.detection_key,
                key.recognition_key,
                key.hf_revision,
            )
            return doctr_support.get_default_doctr_predictor()

        predictor = doctr_support.get_finetuned_torch_doctr_predictor(
            weights.detection_path,
            weights.recognition_path,
            vocab=weights.recognition_vocab,
        )
        if predictor is None:
            raise PredictorBuildError(
                f"Failed to load fine-tuned DocTR weights for "
                f"detection={key.detection_key!r}, "
                f"recognition={key.recognition_key!r}, "
                f"hf_revision={key.hf_revision!r}"
            )
        return predictor


__all__ = [
    "PredictorBuildError",
    "PredictorCache",
    "PredictorKey",
    "ResolvedWeights",
    "WeightsResolver",
]
