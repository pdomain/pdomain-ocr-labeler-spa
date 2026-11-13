"""Pinned labeling-bundle contract.

The version and schema hash are literals. They come from
``pdomain_book_tools.schemas.emit.emit_schema_manifest`` for the released
book-tools package this SPA depends on. A newer package does not move the
pin until this module changes.
"""

from __future__ import annotations

import functools

from pdomain_book_tools.schemas.emit import emit_schema_manifest
from pdomain_book_tools.typography import LabelingBundle

LABELING_BUNDLE_SCHEMA_VERSION = "0.25.0"
LABELING_BUNDLE_SCHEMA_SHA256 = "8f6314b0df042d6bbab49d9d5d5719214fb7c499a5014b1b20058b557db2b631"


@functools.cache
def _installed_schema_matches_pin() -> bool:
    manifest = emit_schema_manifest()
    return (
        manifest["schema_version"] == LABELING_BUNDLE_SCHEMA_VERSION
        and manifest["schema_sha256"] == LABELING_BUNDLE_SCHEMA_SHA256
    )


def require_pinned_labeling_bundle(bundle: LabelingBundle) -> None:
    """Reject a bundle whose schema is not the pinned contract."""
    if bundle.schema_version != LABELING_BUNDLE_SCHEMA_VERSION:
        raise ValueError("labeling bundle schema version is not the pinned contract")
    if not _installed_schema_matches_pin():
        raise ValueError("installed labeling schema is not the pinned contract")


__all__ = [
    "LABELING_BUNDLE_SCHEMA_SHA256",
    "LABELING_BUNDLE_SCHEMA_VERSION",
    "require_pinned_labeling_bundle",
]
