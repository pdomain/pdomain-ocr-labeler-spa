"""Tests for ``core/ocr/predictor.py`` — keyed predictor cache.

Hermetic: the actual ``pdomain_book_tools.ocr.doctr_support`` factories
are stubbed via ``sys.modules`` injection (same pattern as
``tests/unit/core/test_hf_probe.py``) so the suite never pulls in
torch/DocTR weights or hits HF.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from pdomain_ocr_labeler_spa.core.ocr import predictor as predictor_mod
from pdomain_ocr_labeler_spa.core.ocr.predictor import (
    PredictorBuildError,
    PredictorCache,
    PredictorKey,
)


@pytest.fixture
def stub_doctr_support(monkeypatch: pytest.MonkeyPatch):
    """Inject a fake ``pdomain_book_tools.ocr.doctr_support`` module.

    Returns the namespace so individual tests can swap factory
    behavior. ``call_log`` records every factory invocation.
    """

    call_log: list[dict[str, Any]] = []

    def _add_to(obj: SimpleNamespace) -> SimpleNamespace:
        """Attach a torch-``Module``-shaped ``.to(device)``: mutates + returns self."""
        obj.to_calls = []

        def _to(device: str) -> SimpleNamespace:
            obj.to_calls.append(device)
            obj.device = device
            return obj

        obj.to = _to
        obj.device = None
        return obj

    def _make_stock() -> object:
        call_log.append({"factory": "stock"})
        return _add_to(SimpleNamespace(kind="stock", id=len(call_log)))

    def _make_finetuned(det_path: str, reco_path: str, *, vocab: str = "") -> object:
        call_log.append(
            {
                "factory": "finetuned",
                "det_path": det_path,
                "reco_path": reco_path,
                "vocab": vocab,
            }
        )
        return _add_to(SimpleNamespace(kind="finetuned", det=det_path, reco=reco_path, id=len(call_log)))

    fake_module = SimpleNamespace(
        get_default_doctr_predictor=_make_stock,
        get_finetuned_torch_doctr_predictor=_make_finetuned,
    )
    monkeypatch.setitem(sys.modules, "pdomain_book_tools.ocr.doctr_support", fake_module)
    return SimpleNamespace(module=fake_module, calls=call_log)


def test_predictor_key_is_frozen_hashable() -> None:
    k = PredictorKey(detection_key="stock", recognition_key="stock", hf_revision=None)
    assert hash(k) == hash(PredictorKey(detection_key="stock", recognition_key="stock", hf_revision=None))
    with pytest.raises((AttributeError, TypeError)):  # frozen dataclass rejects mutation
        k.detection_key = "other"  # type: ignore[misc]


def test_stock_keys_route_to_default_factory(stub_doctr_support) -> None:
    cache = PredictorCache()
    p = cache.get_or_create("stock", "stock", None)
    assert p.kind == "stock"
    assert len(stub_doctr_support.calls) == 1


def test_cache_returns_same_predictor_on_second_call(stub_doctr_support) -> None:
    cache = PredictorCache()
    p1 = cache.get_or_create("stock", "stock", None)
    p2 = cache.get_or_create("stock", "stock", None)
    assert p1 is p2  # cache hit, factory not re-invoked
    assert len(stub_doctr_support.calls) == 1


def test_distinct_keys_build_distinct_predictors(stub_doctr_support) -> None:
    cache = PredictorCache()
    cache.get_or_create("stock", "stock", None)
    cache.get_or_create("stock", "stock", "main")  # different revision
    assert len(stub_doctr_support.calls) == 2


def test_hf_revision_is_part_of_cache_key(stub_doctr_support) -> None:
    cache = PredictorCache()
    p_main = cache.get_or_create("stock", "stock", "main")
    p_v2 = cache.get_or_create("stock", "stock", "v2")
    assert p_main is not p_v2


def test_clear_drops_cached_entries(stub_doctr_support) -> None:
    cache = PredictorCache()
    cache.get_or_create("stock", "stock", None)
    cache.clear()
    cache.get_or_create("stock", "stock", None)
    assert len(stub_doctr_support.calls) == 2


def test_finetuned_route_when_local_paths_resolved(stub_doctr_support) -> None:
    """Non-stock keys route through the finetuned factory.

    The cache resolves det/reco/vocab via a ``WeightsResolver`` callable
    so the cache itself stays I/O-free; tests inject a simple resolver.
    """

    def resolver(detection_key: str, recognition_key: str, hf_revision: str | None):
        # Return finetuned weight tuple for any non-stock key.
        return predictor_mod.ResolvedWeights(
            detection_path="/models/det.pt",
            recognition_path="/models/reco.pt",
            recognition_vocab="abc",
        )

    cache = PredictorCache(weights_resolver=resolver)
    p = cache.get_or_create("local:all", "local:all", None)
    assert p.kind == "finetuned"
    assert stub_doctr_support.calls[0]["det_path"] == "/models/det.pt"
    assert stub_doctr_support.calls[0]["vocab"] == "abc"


def test_finetuned_failure_raises_predictor_build_error(stub_doctr_support) -> None:
    """If the finetuned factory returns ``None``, surface a
    ``PredictorBuildError`` — legacy parity with
    ``page_operations.py:294-295``."""

    def factory_returns_none(*args: Any, **kwargs: Any) -> object | None:
        return None

    stub_doctr_support.module.get_finetuned_torch_doctr_predictor = factory_returns_none

    def resolver(d: str, r: str, hf: str | None) -> predictor_mod.ResolvedWeights:
        return predictor_mod.ResolvedWeights(
            detection_path="/x/det.pt",
            recognition_path="/x/reco.pt",
            recognition_vocab="abc",
        )

    cache = PredictorCache(weights_resolver=resolver)
    with pytest.raises(PredictorBuildError):
        cache.get_or_create("local:x", "local:x", None)


def test_stock_when_resolver_returns_none(stub_doctr_support) -> None:
    """Resolver returning ``None`` falls back to stock — matches legacy
    ``page_operations.py:297-302`` (if HF/local paths missing → stock)."""

    def resolver(d: str, r: str, hf: str | None) -> None:
        return None

    cache = PredictorCache(weights_resolver=resolver)
    p = cache.get_or_create("hf", "hf", None)
    assert p.kind == "stock"


def test_default_resolver_returns_none(stub_doctr_support) -> None:
    """The cache's default ``weights_resolver`` is a stock-only stub —
    real resolver wiring (HF download + local discovery) is a later
    slice. The default must not silently route to finetuned."""

    cache = PredictorCache()
    p = cache.get_or_create("local:foo", "local:foo", None)
    assert p.kind == "stock"


def test_device_resolver_moves_stock_predictor_via_to(stub_doctr_support) -> None:
    cache = PredictorCache(device_resolver=lambda: "cuda:0")

    p = cache.get_or_create("stock", "stock", None)

    assert p.to_calls == ["cuda:0"]
    assert p.device == "cuda:0"


def test_device_resolver_reapplied_on_cache_hit_when_device_changes(stub_doctr_support) -> None:
    devices = iter(["cuda:0", "cpu"])
    cache = PredictorCache(device_resolver=lambda: next(devices))

    p1 = cache.get_or_create("stock", "stock", None)
    p2 = cache.get_or_create("stock", "stock", None)

    assert p1 is p2  # cache hit — same object, .to() mutates and returns self
    assert p1.to_calls == ["cuda:0", "cpu"]
    assert len(stub_doctr_support.calls) == 1  # only one factory build (cache hit path)


def test_no_device_resolver_never_calls_to(stub_doctr_support) -> None:
    cache = PredictorCache()

    p = cache.get_or_create("stock", "stock", None)

    assert p.to_calls == []


def test_device_resolver_returning_none_skips_to(stub_doctr_support) -> None:
    cache = PredictorCache(device_resolver=lambda: None)

    p = cache.get_or_create("stock", "stock", None)

    assert p.to_calls == []


def test_device_resolver_to_failure_is_swallowed(stub_doctr_support) -> None:
    def _broken_stock() -> object:
        def _raise_to(device: str) -> object:
            raise RuntimeError("cuda oom")

        return SimpleNamespace(kind="stock", to=_raise_to)

    stub_doctr_support.module.get_default_doctr_predictor = _broken_stock
    cache = PredictorCache(device_resolver=lambda: "cuda:0")

    p = cache.get_or_create("stock", "stock", None)

    assert p.kind == "stock"
