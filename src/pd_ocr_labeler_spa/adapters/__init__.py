"""Adapter axes per ``specs/02-backend.md §1, §7``.

Three axes selected by ``Settings``:

- ``storage`` — ``filesystem`` (v1) / ``s3`` (NotImplementedYet, D-019).
- ``auth`` — ``none`` (v1).
- ``ocr`` — ``local_doctr`` (v1, body filled in M3) /
  ``modal`` / ``shared_container`` (both NotImplementedYet, D-018).

The Protocol surface is what every backend conforms to — flipping
``Settings.{storage_backend,auth_mode,ocr_engine}`` becomes a wiring
change in ``bootstrap.py`` rather than per-call-site refactoring.
"""
