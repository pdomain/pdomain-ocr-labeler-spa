"""Domain-level exceptions for ``pd-ocr-labeler-spa``.

Spec naming: ``NotImplementedYet`` (per ``specs/02-backend.md §7``,
``§10``, ``specs/17-decisions.md D-018``, ``D-019``) marks adapter
seams that are wired in shape but whose v1 impl raises rather than
delivers — e.g. the ``s3`` storage backend or the ``modal`` /
``shared_container`` OCR engines. It subclasses ``NotImplementedError``
so generic except-clauses still catch it, but greppable by name so
"this is a deliberate seam" is distinguishable from "this is a TODO
inside something otherwise complete".

``BoundingBoxGeometryError`` (per ``specs/02-backend.md §8``) is the
one labeler-specific addition to pgdp-prep's verbatim error chain:
geometry-normalization failures (degenerate / non-finite / inverted
boxes) surfaced from the OCR / refine paths must come back to the SPA
as ``422 geometry_error`` so the toolbar can surface a human-readable
toast rather than a generic 500. The handler chain in
``api/middleware/error_handler.py`` matches this exception class
explicitly — keep it here (not at a use-site) so route code can ``from
.core.exceptions import BoundingBoxGeometryError`` without circular
imports.

``IncompatibleEnvelopeError`` (per ``specs/09-persistence.md §11``)
is raised when ``parse_envelope`` encounters a schema version it does
not recognise. The error handler maps this to ``422
incompatible_envelope`` so the SPA toast layer can show a targeted
"Upgrade to read this file" message rather than a generic 500. The
``version`` attribute carries the version string from the file; the
``supported`` attribute carries the list of versions this binary can
read — both are emitted in the error response body so the SPA doesn't
need to string-parse the message.
"""

from __future__ import annotations


class NotImplementedYet(NotImplementedError):  # noqa: N818  # intentional name: a "not yet" sentinel, not an error-type label
    """Adapter / endpoint exists in shape; v1 impl deliberately deferred.

    Raise from a stubbed backend method when the user has selected it via
    ``Settings`` — the message should name the seam (``"modal OCR adapter
    not yet wired"``) so the failure mode is self-explanatory.
    """


class BoundingBoxGeometryError(ValueError):
    """A bounding box failed geometry normalization.

    Raised by OCR / refine code paths when a box is degenerate (zero or
    negative width/height), non-finite, inverted, or otherwise
    un-normalisable to the unit square. The error handler in
    ``api/middleware/error_handler.py`` maps this to ``422
    geometry_error`` per ``specs/02-backend.md §8`` — distinct from the
    generic 500 catch-all so the SPA can render a targeted toast.

    Subclasses ``ValueError`` so that any code path that catches
    ``ValueError`` for "invalid input" already handles this case
    correctly.
    """


class IncompatibleEnvelopeError(ValueError):
    """A ``UserPageEnvelope`` file has a schema version this binary cannot read.

    Raised by ``parse_envelope`` when the ``schema.version`` field is not
    in the set of supported versions (currently ``{"2.1", "2.2"}``).  The
    error handler in ``api/middleware/error_handler.py`` maps this to
    ``422 incompatible_envelope`` so the SPA toast layer can show a
    targeted "Upgrade to read this file" message rather than a generic 500.

    Attributes
    ----------
    version
        The version string found in the file (e.g. ``"3.0"``).
    supported
        The list of version strings this binary can read (e.g.
        ``["2.1", "2.2"]``).  Emitted in the error response body.
    """

    def __init__(self, *, version: str, supported: list[str]) -> None:
        self.version = version
        self.supported = supported
        supported_str = ", ".join(supported)
        super().__init__(
            f"UserPageEnvelope schema version {version!r} is not supported by this binary "
            f"(supported: {supported_str}). "
            "This page was likely saved by a newer pd-ocr-labeler. "
            "Upgrade to read it."
        )
