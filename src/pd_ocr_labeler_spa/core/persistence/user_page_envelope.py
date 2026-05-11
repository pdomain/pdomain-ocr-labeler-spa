"""Reader/writer for ``UserPageEnvelope`` v2.1 on-disk shape.

Spec authority:

- ``specs/01-data-models.md §3`` lines 503–576 — ``UserPageEnvelope``
  v2.1 / v2.2 wire shape + reader API.
- ``specs/09-persistence.md §2`` lines 44–110 — schema, reader surface,
  round-trip identity invariant.

**Byte-compat target.** Legacy
``pd-ocr-labeler/pd_ocr_labeler/models/user_page_persistence.py``.
The SPA and legacy share the on-disk envelope file under D-003: both
binaries read+write the labeled lane (``<data_root>/labeled-projects/
<project_id>/<project_id>_<page:03d>.json``), so the dataclass shape,
field names, optional-field omission rules, and permissive-coercion
semantics MUST match legacy ``UserPageEnvelope.from_dict`` /
``to_dict`` exactly.

What this slice (8b-iii) ships:

- ``UserPageEnvelope`` + nested dataclasses (``UserPageSchema``,
  ``UserPageProvenance``, ``ProvenanceApp``, ``ProvenanceToolchain``,
  ``OCRProvenance``, ``OCRModelProvenance``, ``UserPageSource``,
  ``SourceImageFingerprint``, ``UserPagePayload``).
- ``is_user_page_envelope(data) -> bool`` — type guard checking
  ``data["schema"]["name"] == USER_PAGE_SCHEMA_NAME``.
- ``parse_envelope(data) -> UserPageEnvelope`` — permissive reader,
  legacy ``from_dict`` semantics.
- ``envelope_to_dict(envelope) -> dict`` — writer, mirroring legacy
  ``to_dict`` (omits empty/None optional fields per legacy).

Round-trip identity (the D-003 invariant): for any envelope the
legacy labeler wrote, ``envelope_to_dict(parse_envelope(data)) == data``
(modulo Python-3.7+ ordered-dict guarantees).

Deferred to later slices:

- ``build_envelope(...)`` — the high-level constructor that takes a
  ``Page`` object + ``Project`` + freshly-built ``OCRProvenance`` and
  produces the envelope. Needs ``pd_book_tools.Page`` in scope; ships
  with the auto-cache-write slice.
- v2.2 rotation fields (``source.rotation_degrees`` /
  ``source.rotation_source``). The reader silently tolerates these via
  the legacy ``.get()`` pattern (no ``extra="forbid"`` here — D-003
  parity is more important than forward-compat strictness; legacy is
  the schema authority and legacy is permissive). Adding explicit
  fields for them lands with M9.

Module-name policy: ``user_page_envelope`` (singular envelope) per
``specs/01-data-models.md`` line 567 + ``specs/09-persistence.md`` line
79. Legacy was ``user_page_persistence`` — renamed in the SPA so the
filename describes the shape, not the verb.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pd_ocr_labeler_spa.core.persistence.paths import (
    image_cache_root,
    labeled_projects_root,
)

logger = logging.getLogger(__name__)

USER_PAGE_SCHEMA_NAME = "pd_ocr_labeler.user_page"
USER_PAGE_SCHEMA_VERSION = "2.1"

# Legacy default-value sentinels. Lifted to module scope so writers
# producing an envelope from scratch can reuse them without re-typing
# the literals (drift hazard).
USER_PAGE_SOURCE_LANE_LABELED = "labeled"
USER_PAGE_SOURCE_LANE_CACHED = "cached"
USER_PAGE_SAVED_BY_SAVE_PAGE = "Save Page"
UNKNOWN_METADATA_VALUE = "unknown"


# ── ocr provenance ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class OCRModelProvenance:
    """Per-model metadata inside ``provenance.ocr.models[]``.

    Legacy ref: ``user_page_persistence.py:11-36``.
    """

    name: str
    version: str | None = None
    weights_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name}
        if self.version:
            result["version"] = self.version
        if self.weights_id:
            result["weights_id"] = self.weights_id
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCRModelProvenance:
        return cls(
            name=str(data.get("name", "unknown")),
            version=(str(data["version"]) if data.get("version") is not None else None),
            weights_id=(str(data["weights_id"]) if data.get("weights_id") is not None else None),
        )


@dataclass(frozen=True)
class OCRProvenance:
    """``provenance.ocr`` block.

    Legacy ref: ``user_page_persistence.py:38-80``. The
    ``models`` list is permissive on read: dict entries become
    ``OCRModelProvenance``; bare non-empty strings become
    ``OCRModelProvenance(name=...)`` (legacy parity for very old
    saves); everything else is silently dropped.
    """

    engine: str = UNKNOWN_METADATA_VALUE
    engine_version: str | None = None
    models: list[OCRModelProvenance] = field(default_factory=list)
    config_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "engine": self.engine,
            "models": [model.to_dict() for model in self.models],
        }
        if self.engine_version:
            result["engine_version"] = self.engine_version
        if self.config_fingerprint:
            result["config_fingerprint"] = self.config_fingerprint
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OCRProvenance:
        raw_models = data.get("models", [])
        models: list[OCRModelProvenance] = []
        if isinstance(raw_models, list):
            for model in raw_models:
                if isinstance(model, dict):
                    models.append(OCRModelProvenance.from_dict(model))
                elif isinstance(model, str) and model:
                    models.append(OCRModelProvenance(name=model))
        return cls(
            engine=str(data.get("engine", UNKNOWN_METADATA_VALUE)),
            engine_version=(str(data["engine_version"]) if data.get("engine_version") is not None else None),
            models=models,
            config_fingerprint=(
                str(data["config_fingerprint"]) if data.get("config_fingerprint") is not None else None
            ),
        )


# ── schema + provenance ──────────────────────────────────────────────────


@dataclass(frozen=True)
class UserPageSchema:
    """``envelope["schema"]`` block. Legacy ref: lines 93-106."""

    name: str = USER_PAGE_SCHEMA_NAME
    version: str = USER_PAGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserPageSchema:
        return cls(
            name=str(data.get("name", USER_PAGE_SCHEMA_NAME)),
            version=str(data.get("version", USER_PAGE_SCHEMA_VERSION)),
        )


@dataclass(frozen=True)
class ProvenanceApp:
    """``provenance.app`` block. Legacy ref: lines 109-132.

    Note: the SPA writes ``name="pd_ocr_labeler_spa"`` for new saves
    (per spec §3 line 530), but the **default** here matches legacy's
    default so a parse of a missing ``app`` block round-trips to the
    legacy default. The writer (``build_envelope``, M3 follow-on
    slice) is responsible for setting ``name="pd_ocr_labeler_spa"``
    explicitly when constructing a fresh envelope.
    """

    name: str = "pd_ocr_labeler"
    version: str = UNKNOWN_METADATA_VALUE
    git_commit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
        }
        if self.git_commit:
            result["git_commit"] = self.git_commit
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvenanceApp:
        return cls(
            name=str(data.get("name", "pd_ocr_labeler")),
            version=str(data.get("version", UNKNOWN_METADATA_VALUE)),
            git_commit=(str(data["git_commit"]) if data.get("git_commit") is not None else None),
        )


@dataclass(frozen=True)
class ProvenanceToolchain:
    """``provenance.toolchain`` block. Legacy ref: lines 135-160."""

    python: str = UNKNOWN_METADATA_VALUE
    pd_book_tools: str = UNKNOWN_METADATA_VALUE
    opencv_python: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "python": self.python,
            "pd_book_tools": self.pd_book_tools,
        }
        if self.opencv_python:
            result["opencv_python"] = self.opencv_python
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvenanceToolchain:
        return cls(
            python=str(data.get("python", UNKNOWN_METADATA_VALUE)),
            pd_book_tools=str(data.get("pd_book_tools", UNKNOWN_METADATA_VALUE)),
            opencv_python=(str(data["opencv_python"]) if data.get("opencv_python") is not None else None),
        )


@dataclass(frozen=True)
class UserPageProvenance:
    """``envelope["provenance"]`` block. Legacy ref: lines 167-195."""

    saved_at: str = ""
    saved_by: str = USER_PAGE_SAVED_BY_SAVE_PAGE
    source_lane: str = USER_PAGE_SOURCE_LANE_LABELED
    app: ProvenanceApp = field(default_factory=ProvenanceApp)
    toolchain: ProvenanceToolchain = field(default_factory=ProvenanceToolchain)
    ocr: OCRProvenance = field(default_factory=OCRProvenance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "saved_at": self.saved_at,
            "saved_by": self.saved_by,
            "source_lane": self.source_lane,
            "app": self.app.to_dict(),
            "toolchain": self.toolchain.to_dict(),
            "ocr": self.ocr.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserPageProvenance:
        app_data = data.get("app", {})
        toolchain_data = data.get("toolchain", {})
        ocr_data = data.get("ocr", {})
        return cls(
            saved_at=str(data.get("saved_at", "")),
            saved_by=str(data.get("saved_by", USER_PAGE_SAVED_BY_SAVE_PAGE)),
            source_lane=str(data.get("source_lane", USER_PAGE_SOURCE_LANE_LABELED)),
            app=ProvenanceApp.from_dict(app_data if isinstance(app_data, dict) else {}),
            toolchain=ProvenanceToolchain.from_dict(
                toolchain_data if isinstance(toolchain_data, dict) else {}
            ),
            ocr=OCRProvenance.from_dict(ocr_data if isinstance(ocr_data, dict) else {}),
        )


# ── source ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceImageFingerprint:
    """``envelope["source"]["image_fingerprint"]``. Legacy ref: 198-222."""

    size: int | None = None
    mtime_ns: int | None = None
    sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.size is not None:
            result["size"] = self.size
        if self.mtime_ns is not None:
            result["mtime_ns"] = self.mtime_ns
        if self.sha256 is not None:
            result["sha256"] = self.sha256
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceImageFingerprint:
        return cls(
            size=int(data["size"]) if data.get("size") is not None else None,
            mtime_ns=(int(data["mtime_ns"]) if data.get("mtime_ns") is not None else None),
            sha256=(str(data["sha256"]) if data.get("sha256") is not None else None),
        )


@dataclass(frozen=True)
class UserPageSource:
    """``envelope["source"]`` block. Legacy ref: 225-266.

    v2.2 rotation fields (``rotation_degrees`` / ``rotation_source``)
    are silently passed through the reader via ``.get()`` semantics —
    they are NOT explicit dataclass fields at this slice. M9 wires
    them when manual + auto rotation lands.
    """

    project_id: str = ""
    page_index: int = 0
    page_number: int = 0
    image_path: str = ""
    project_root: str | None = None
    image_fingerprint: SourceImageFingerprint | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "project_id": self.project_id,
            "page_index": self.page_index,
            "page_number": self.page_number,
            "image_path": self.image_path,
        }
        if self.project_root:
            result["project_root"] = self.project_root
        if self.image_fingerprint:
            result["image_fingerprint"] = self.image_fingerprint.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserPageSource:
        fingerprint_data = data.get("image_fingerprint")
        image_fingerprint = (
            SourceImageFingerprint.from_dict(fingerprint_data) if isinstance(fingerprint_data, dict) else None
        )
        return cls(
            project_id=str(data.get("project_id", "")),
            page_index=int(data.get("page_index", 0)),
            page_number=int(data.get("page_number", 0)),
            image_path=str(data.get("image_path", "")),
            project_root=(str(data["project_root"]) if data.get("project_root") is not None else None),
            image_fingerprint=image_fingerprint,
        )


# ── payload ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserPagePayload:
    """``envelope["payload"]`` block. Legacy ref: 269-309.

    ``page`` is the verbatim ``pd_book_tools.ocr.page.Page.to_dict()``
    output. We hold it as a plain ``dict`` here so this module can be
    imported without pd_book_tools (slice 8b deferral pattern); the
    high-level ``build_envelope`` constructor (later slice) is the
    layer that converts ``Page`` → ``page_dict``.

    ``word_attributes`` reading mirrors legacy semantics:

    - non-dict input → ``None``
    - non-string keys → entry dropped
    - non-dict values → entry dropped
    - within each entry, attr values coerced via ``bool(...)`` (legacy
      lines 298-302).
    """

    page: dict[str, Any] = field(default_factory=dict)
    original_page: dict[str, Any] | None = None
    word_attributes: dict[str, dict[str, bool]] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"page": self.page}
        if self.original_page is not None:
            result["original_page"] = self.original_page
        if self.word_attributes is not None:
            result["word_attributes"] = self.word_attributes
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserPagePayload:
        page_data = data.get("page")
        if not isinstance(page_data, dict):
            page_data = {}
        original_page_data = data.get("original_page")
        if original_page_data is not None and not isinstance(original_page_data, dict):
            original_page_data = None
        raw_word_attributes = data.get("word_attributes")
        word_attributes: dict[str, dict[str, bool]] | None = None
        if isinstance(raw_word_attributes, dict):
            normalized: dict[str, dict[str, bool]] = {}
            for key, value in raw_word_attributes.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                normalized[key] = {
                    str(attr_name): bool(attr_value)
                    for attr_name, attr_value in value.items()
                    if isinstance(attr_name, str)
                }
            word_attributes = normalized
        return cls(
            page=page_data,
            original_page=original_page_data,
            word_attributes=word_attributes,
        )


# ── top-level envelope ───────────────────────────────────────────────────


@dataclass(frozen=True)
class UserPageEnvelope:
    """Top-level envelope dataclass. Legacy ref: 312-350."""

    schema: UserPageSchema = field(default_factory=UserPageSchema)
    provenance: UserPageProvenance = field(default_factory=UserPageProvenance)
    source: UserPageSource = field(default_factory=UserPageSource)
    payload: UserPagePayload = field(default_factory=UserPagePayload)
    cached_images: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema": self.schema.to_dict(),
            "provenance": self.provenance.to_dict(),
            "source": self.source.to_dict(),
            "payload": self.payload.to_dict(),
        }
        if self.cached_images:
            result["cached_images"] = dict(self.cached_images)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserPageEnvelope:
        raw_cached = data.get("cached_images", {})
        cached_images: dict[str, str] = {}
        if isinstance(raw_cached, dict):
            cached_images = {
                str(k): str(v)
                for k, v in raw_cached.items()
                if isinstance(k, str) and isinstance(v, str) and k and v
            }
        schema_data = data.get("schema", {})
        provenance_data = data.get("provenance", {})
        source_data = data.get("source", {})
        payload_data = data.get("payload", {})
        return cls(
            schema=UserPageSchema.from_dict(schema_data if isinstance(schema_data, dict) else {}),
            provenance=UserPageProvenance.from_dict(
                provenance_data if isinstance(provenance_data, dict) else {}
            ),
            source=UserPageSource.from_dict(source_data if isinstance(source_data, dict) else {}),
            payload=UserPagePayload.from_dict(payload_data if isinstance(payload_data, dict) else {}),
            cached_images=cached_images,
        )


# ── public functional API ────────────────────────────────────────────────


def is_user_page_envelope(data: dict[str, Any]) -> bool:
    """Type guard — does ``data`` look like a ``UserPageEnvelope``?

    Checks ``data["schema"]["name"] == USER_PAGE_SCHEMA_NAME``. Does NOT
    validate version (callers should accept v2.1 + v2.2 + future
    additive bumps; the parser handles the "future field unknown to
    me" case via permissive ``.get()`` semantics).

    Legacy ref: ``user_page_persistence.py:353-357``.
    """
    schema = data.get("schema")
    if not isinstance(schema, dict):
        return False
    return str(schema.get("name")) == USER_PAGE_SCHEMA_NAME


def parse_envelope(data: dict[str, Any]) -> UserPageEnvelope:
    """Permissive reader. Missing keys fall back to defaults. Same
    failure-mode contract as legacy ``UserPageEnvelope.from_dict``:
    never raises on shape mismatch; coerces or substitutes defaults
    silently.

    Callers that want the type-guard check before parsing should call
    ``is_user_page_envelope(data)`` first.
    """
    return UserPageEnvelope.from_dict(data)


def envelope_to_dict(envelope: UserPageEnvelope) -> dict[str, Any]:
    """Serialise back to a JSON-ready dict. Legacy parity:

    - empty ``cached_images`` is omitted from the output (line 330-331).
    - ``payload.original_page`` is omitted when ``None`` (line 277-278).
    - ``payload.word_attributes`` is omitted when ``None`` (line 279-280).
    - ``provenance.app.git_commit`` is omitted when ``None`` (line 120-121).
    - ``provenance.toolchain.opencv_python`` is omitted when ``None`` (line 146-147).
    - ``provenance.ocr.engine_version`` and ``config_fingerprint`` are
      omitted when ``None`` (line 50-53).
    - ``source.project_root`` and ``source.image_fingerprint`` are
      omitted when ``None``/empty (line 241-244).
    - ``SourceImageFingerprint`` only emits non-None subfields.

    These omission rules are what produce the round-trip-identity
    invariant: legacy never writes ``"original_page": null``, so the
    SPA must not either, otherwise re-saved files diverge from
    legacy-saved files in the same project.
    """
    return envelope.to_dict()


# ── path helpers (slice 8b-iv) ───────────────────────────────────────────


def _envelope_filename(project_id: str, page_index: int) -> str:
    """``<project_id>_<page:03d>.json`` — legacy parity, used as the base
    filename for the labeled lane (legacy ``page_operations.py:444``)."""
    page_number = page_index + 1
    return f"{project_id}_{page_number:03d}.json"


def labeled_envelope_path(data_root: Path, project_id: str, page_index: int) -> Path:
    """Path to the labeled-lane envelope file.

    Spec: ``specs/09-persistence.md §1`` line 22 —
    ``<data_root>/labeled-projects/<project_id>/<project_id>_<page:03d>.json``.

    Page numbering is 1-based zero-padded to **at least** three digits
    (legacy ``page_operations.py:430,444`` — ``page_number = index + 1``,
    formatted via ``{:03d}`` which is a *minimum* width). This is shared
    on disk with the legacy labeler under D-003.
    """
    return labeled_projects_root(data_root) / project_id / _envelope_filename(project_id, page_index)


def cached_envelope_path(cache_root: Path, project_id: str, page_index: int) -> Path:
    """Path to the cached-lane envelope file.

    Spec: ``specs/09-persistence.md §1`` line 28 + §4.2 line 161 —
    ``<cache_root>/page-images/<project_id>_<page:03d>_envelope.json``.

    The ``_envelope`` suffix is **SPA-specific**: legacy writes plain
    ``<project_id>_<page:03d>.json`` to this same dir, so the suffix
    avoids collision when both binaries write to the shared cache dir
    (D-003). The SPA only reads/writes its own ``_envelope.json``
    files; the per-image-type cache files
    (``<project>_<page:03d>_<image_type>_<sha>.{jpg,png}``) are still
    legacy-shared because the content-addressed names can't collide.
    """
    page_number = page_index + 1
    return image_cache_root(cache_root) / f"{project_id}_{page_number:03d}_envelope.json"


def read_envelope_file(path: Path) -> UserPageEnvelope | None:
    """Read + parse an envelope file from disk. Failure-mode-tolerant.

    Returns ``None`` for every failure path (file missing, unparsable
    JSON, non-dict root, schema-name mismatch). Never raises. Same
    contract shape as ``persistence/session_state.load_session_state``;
    rationale: per spec §9 lines 32–40, the load-precedence dispatcher
    falls through to the next lane (cached / OCR) on a failed read,
    and that fall-through must not be gated on raised exceptions.

    Failure paths emit a DEBUG-level log so a corrupt file shows up in
    debug traces but doesn't pollute INFO.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("envelope read failed: %s (%s)", path, exc)
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.debug("envelope JSON parse failed: %s (%s)", path, exc)
        return None
    if not isinstance(data, dict):
        logger.debug("envelope root is not a dict: %s", path)
        return None
    if not is_user_page_envelope(data):
        logger.debug("envelope schema name mismatch (not a user_page envelope): %s", path)
        return None
    return parse_envelope(data)


# ── high-level constructor (build_envelope writer) ───────────────────────


_SPA_APP_NAME = "pd_ocr_labeler_spa"


def _safe_package_version(name: str) -> str:
    """Best-effort package version lookup. Mirrors legacy
    ``page_operations._safe_package_version`` semantics: returns the
    installed version string or ``"unknown"`` on any error.

    Lifted into envelope module so ``build_envelope`` can populate
    provenance without reaching into the operations layer.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version(name)
        except PackageNotFoundError:
            return UNKNOWN_METADATA_VALUE
    except Exception:  # pragma: no cover - defensive
        return UNKNOWN_METADATA_VALUE


def _now_iso_z() -> str:
    """Current UTC time as ISO8601 with ``Z`` suffix.

    Legacy parity (``page_operations.py:1160``):
    ``datetime.now(UTC).isoformat().replace("+00:00", "Z")``.
    """
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _python_version() -> str:
    """``major.minor.micro`` per legacy line 1163."""
    import sys

    info = sys.version_info
    return f"{info.major}.{info.minor}.{info.micro}"


def build_envelope(
    *,
    page: Any,
    project: Any,  # core.models.Project — typed Any to avoid circular import
    page_index: int,
    ocr_provenance: OCRProvenance,
    source_lane: str = USER_PAGE_SOURCE_LANE_LABELED,
    saved_at: str | None = None,
    saved_by: str = USER_PAGE_SAVED_BY_SAVE_PAGE,
    cached_images: dict[str, str] | None = None,
    word_attributes: dict[str, dict[str, bool]] | None = None,
    original_page: dict[str, Any] | None = None,
) -> UserPageEnvelope:
    """High-level envelope constructor.

    Composes a ``UserPageEnvelope`` from a ``Page``-like object (anything
    with ``to_dict() -> dict``), the bound ``Project``, and selection
    metadata. Legacy ref:
    ``pd-ocr-labeler/pd_ocr_labeler/operations/ocr/page_operations.py:1141-1183``
    (``_build_user_page_envelope``).

    Parameters
    ----------
    page
        A ``pd_book_tools.ocr.page.Page`` (or any object exposing
        ``to_dict()``). Tests inject a stub. The dict is placed verbatim
        into ``payload.page``; this function never inspects its
        contents.
    project
        The bound ``core.models.Project``. Used for ``project_id`` and
        the page filename via ``project.image_paths[page_index].name``.
    page_index
        0-based index into ``project.image_paths``. ``page_number``
        becomes ``page_index + 1`` (legacy line 1145).
    ocr_provenance
        Pre-built ``OCRProvenance`` (engine + models + version). The
        caller is responsible for assembling this from the
        ``OCRConfigCarrier`` snapshot + ``PredictorCache`` keys.
    source_lane
        ``"labeled"`` (default; user-saved files) or ``"cached"``
        (auto-cache writer after first OCR). Drives the lane the file
        is written to and the metadata read by the labeler when it
        re-loads the file.
    saved_at
        ISO8601-with-``Z`` timestamp. Defaults to ``datetime.now(UTC)``
        formatted to match legacy. Caller can pin a value (deterministic
        tests; route layer wanting one shared timestamp across pages).
    saved_by
        Free-form provenance label; default matches legacy "Save Page".
    cached_images
        Map of cached image variant filenames (e.g.
        ``{"corrected": "proj_001_corrected_<sha>.jpg"}``). When empty
        the writer omits the key from the JSON output (legacy parity).
    word_attributes
        Per-word attribute map; ``None`` omits the field on write.
    original_page
        Pre-edit ``Page.to_dict()`` snapshot (used by labeler's diff/
        revert flow); ``None`` omits the field.

    Returns
    -------
    UserPageEnvelope
        The composed envelope. Pass it to :func:`envelope_to_dict` to
        get the JSON-ready dict.

    Raises
    ------
    IndexError
        If ``page_index`` is out of range for ``project.image_paths``.
        Mirrors :class:`LocalDoctrPageLoader.run_ocr`'s shape — the two
        places that index into image_paths use the same exception type.

    Notes
    -----
    - ``app.name`` is hardcoded to ``"pd_ocr_labeler_spa"`` (spec §3
      line 530); legacy writes ``"pd_ocr_labeler"``. The reader accepts
      either, so D-003 round-trip identity holds for legacy-written
      files (the reader doesn't normalise the name).
    - ``app.version`` and ``toolchain.python`` / ``toolchain.pd_book_tools``
      are populated from package metadata (legacy line 1161-1164). They
      can be ``"unknown"`` if the package isn't installed via metadata
      (e.g. editable install without metadata) — never raise.
    """
    image_paths = project.image_paths
    if page_index < 0 or page_index >= len(image_paths):
        raise IndexError(f"page_index {page_index} out of range (total_pages={len(image_paths)})")

    image_filename = image_paths[page_index].name

    page_dict = page.to_dict()

    return UserPageEnvelope(
        schema=UserPageSchema(version=USER_PAGE_SCHEMA_VERSION),
        provenance=UserPageProvenance(
            saved_at=saved_at if saved_at is not None else _now_iso_z(),
            saved_by=saved_by,
            source_lane=source_lane,
            app=ProvenanceApp(
                name=_SPA_APP_NAME,
                version=_safe_package_version("pd-ocr-labeler-spa"),
            ),
            toolchain=ProvenanceToolchain(
                python=_python_version(),
                pd_book_tools=_safe_package_version("pd-book-tools"),
            ),
            ocr=ocr_provenance,
        ),
        source=UserPageSource(
            project_id=project.project_id,
            page_index=page_index,
            page_number=page_index + 1,
            image_path=image_filename,
        ),
        payload=UserPagePayload(
            page=page_dict,
            original_page=original_page,
            word_attributes=word_attributes,
        ),
        cached_images=dict(cached_images) if cached_images else {},
    )


__all__ = [
    "UNKNOWN_METADATA_VALUE",
    "USER_PAGE_SAVED_BY_SAVE_PAGE",
    "USER_PAGE_SCHEMA_NAME",
    "USER_PAGE_SCHEMA_VERSION",
    "USER_PAGE_SOURCE_LANE_CACHED",
    "USER_PAGE_SOURCE_LANE_LABELED",
    "OCRModelProvenance",
    "OCRProvenance",
    "ProvenanceApp",
    "ProvenanceToolchain",
    "SourceImageFingerprint",
    "UserPageEnvelope",
    "UserPagePayload",
    "UserPageProvenance",
    "UserPageSchema",
    "UserPageSource",
    "build_envelope",
    "cached_envelope_path",
    "envelope_to_dict",
    "is_user_page_envelope",
    "labeled_envelope_path",
    "parse_envelope",
    "read_envelope_file",
]
