"""Resolve and render the torch device DocTR / pd_book_tools will use.

Used by ``__main__.main`` to print a single startup line so users running
``make run`` (or any direct ``pd-ocr-labeler-ui`` invocation) can see
whether torch picked up the local GPU before they kick off a real OCR
pass.

Design constraints (small but load-bearing):

- **No raises.** The caller emits this string before uvicorn binds, so
  a traceback here would derail server startup. Every failure path
  funnels into a CPU-flavored fallback string.
- **Lazy torch import.** torch is heavy and is pulled in via
  pd_book_tools rather than this repo directly; keep test collection
  fast and ``pd-ocr-labeler-ui --version`` torch-free by deferring
  the import inside the function body.
- **Pure render.** Returns a string; logging / printing is the
  caller's responsibility. Keeps the helper trivially testable
  without capturing stdout.

The returned format intentionally mirrors what the user asked for in
the slice request:

    device: cuda:0 (NVIDIA …)
    device: cpu
    device: cpu (torch unavailable)
    device: cpu (<reason>)
"""

from __future__ import annotations


def describe_device() -> str:
    """Return a one-line description of the resolved torch device.

    Never raises. See module docstring for output forms.
    """
    try:
        import torch  # local import: see module docstring
    except Exception:
        return "device: cpu (torch unavailable)"

    # ``monkeypatch.setitem(sys.modules, "torch", None)`` makes
    # ``import torch`` succeed-but-bind-None. Treat that the same as
    # an outright ImportError so test isolation is easy.
    if torch is None:
        return "device: cpu (torch unavailable)"

    try:
        cuda = torch.cuda
        if not cuda.is_available():
            return "device: cpu"
        idx = cuda.current_device()
        name = cuda.get_device_name(idx)
        return f"device: cuda:{idx} ({name})"
    except Exception as exc:
        # Surface the underlying reason so a misconfigured GPU
        # (e.g. driver mismatch) is at least diagnosable from the
        # startup line.
        return f"device: cpu ({exc})"
