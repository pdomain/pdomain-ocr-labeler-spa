"""Lane A / Task A1 — refine_bboxes job handler registration.

Audit finding: ``POST .../refine`` enqueues job type ``refine_bboxes``,
but it was absent from ``core/jobs/runner._HANDLERS`` → ``NotImplementedError``
at run time. This test pins the registration.
"""

from __future__ import annotations

from pdomain_ocr_labeler_spa.core.jobs.runner import _HANDLERS


def test_refine_bboxes_handler_registered() -> None:
    assert "refine_bboxes" in _HANDLERS
