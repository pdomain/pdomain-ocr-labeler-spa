"""Core OCR helpers — predictor cache, provenance, etc.

Spec: ``specs/02-backend.md §1`` (line 62 — ``predictor.py``) and
``specs/16-milestones.md`` M3 row.

The cache lives here (settings-agnostic, no FastAPI imports) so the
adapter layer (``adapters/ocr/local_doctr.py``) only orchestrates;
swapping caches in tests is a single-keyword override.
"""
