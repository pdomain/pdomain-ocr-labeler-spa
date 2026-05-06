"""Domain-level exceptions for ``pd-ocr-labeler-spa``.

Spec naming: ``NotImplementedYet`` (per ``specs/02-backend.md §7``,
``§10``, ``specs/17-decisions.md D-018``, ``D-019``) marks adapter
seams that are wired in shape but whose v1 impl raises rather than
delivers — e.g. the ``s3`` storage backend or the ``modal`` /
``shared_container`` OCR engines. It subclasses ``NotImplementedError``
so generic except-clauses still catch it, but greppable by name so
"this is a deliberate seam" is distinguishable from "this is a TODO
inside something otherwise complete".
"""

from __future__ import annotations


class NotImplementedYet(NotImplementedError):
    """Adapter / endpoint exists in shape; v1 impl deliberately deferred.

    Raise from a stubbed backend method when the user has selected it via
    ``Settings`` — the message should name the seam (``"modal OCR adapter
    not yet wired"``) so the failure mode is self-explanatory.
    """
