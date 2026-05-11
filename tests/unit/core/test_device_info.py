"""Unit tests for ``core.device_info``.

The helper resolves the torch device that pd_book_tools / DocTR will
pick up at OCR time, and renders it as a one-line string suitable for
``make run`` startup logging. Critically:

- It must NEVER raise — torch may be absent in some test envs and the
  caller (``__main__.main``) prints the result before uvicorn binds, so
  any traceback would mask the real "did the server start?" question.
- It must NOT eagerly import torch at module-import time (keeps test
  collection cheap and lets ``--version`` skip the import entirely).

The function is small and pure aside from a torch lookup; we
monkeypatch the import path rather than relying on the actual
torch install.
"""

from __future__ import annotations

import sys
import types

from pd_ocr_labeler_spa.core import device_info


def test_describe_device_returns_cpu_when_torch_missing(monkeypatch):
    """If torch can't be imported, fall back to ``device: cpu (torch unavailable)``.

    The CPU fallback string is intentional — the caller is asking
    "what device will OCR use?" and the honest answer when torch is
    missing is "CPU, and we don't even have torch to confirm".
    """
    # Hide torch from the import system regardless of whether it's
    # actually installed in this venv.
    monkeypatch.setitem(sys.modules, "torch", None)

    out = device_info.describe_device()

    assert isinstance(out, str)
    assert out.startswith("device: cpu")
    assert "torch unavailable" in out


def test_describe_device_reports_cuda_when_available(monkeypatch):
    """When ``torch.cuda.is_available()`` is True, render the GPU name."""
    fake_torch = types.ModuleType("torch")
    fake_cuda = types.SimpleNamespace(
        is_available=lambda: True,
        get_device_name=lambda idx: "NVIDIA Test GPU",
        current_device=lambda: 0,
    )
    fake_torch.cuda = fake_cuda  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    out = device_info.describe_device()

    assert out.startswith("device: cuda:0")
    assert "NVIDIA Test GPU" in out


def test_describe_device_reports_cpu_when_cuda_unavailable(monkeypatch):
    """torch present but no CUDA → plain ``device: cpu``."""
    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(  # type: ignore[attr-defined]
        is_available=lambda: False,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    out = device_info.describe_device()

    assert out == "device: cpu"


def test_describe_device_swallows_exceptions(monkeypatch):
    """A broken torch (raising on attr access) must not propagate."""

    class _BoomCuda:
        def is_available(self):
            raise RuntimeError("driver mismatch")

    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = _BoomCuda()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    out = device_info.describe_device()

    # We don't pin the exact suffix, just that it's a graceful CPU
    # fallback rather than a traceback.
    assert out.startswith("device: cpu")
    assert "driver mismatch" in out or "unavailable" in out
