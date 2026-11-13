"""OCR and page-region model runs recorded for a geometry-optional bundle.

The runs live on the page event store under ``extensions["labeler.exchange"]``.
Hashes name blobs in that page's blob store. This module does not import
``pdomain_source_data``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal
from uuid import UUID

from eventsourcing.application import AggregateNotFoundError
from eventsourcing.persistence import PersistenceError
from pdomain_book_tools.typography import (
    CoordinateTransform,
    CoordinateTransformStage,
    CorrectionBundle,
    ModelRun,
    ModelRunPurpose,
    PageGeometry,
    ReplacementArtifact,
    SourceOrientation,
    TypographyCorrection,
    WordGeometry,
)
from pdomain_ops.page_aggregate import PageAggregate
from pydantic import BaseModel, ConfigDict, ValidationError

from .persistence.labeling_contract import LABELING_BUNDLE_SCHEMA_VERSION
from .persistence.page_store import LabelerPageStore

log = logging.getLogger(__name__)

EXCHANGE_NAMESPACE = "labeler.exchange"
NIL_PAGE_ID = UUID(int=0)

DOCTR_PREPROCESSING: dict[str, str] = {
    "auto_rotate": "false",
    "coordinate_space": "on_disk_pixels",
    "image_reader": "cv2.imread",
}
_TESSERACT_PSM = "3"
_IDENTITY_AFFINE = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


@dataclass(frozen=True)
class OcrExchangeIdentity:
    """Configured OCR engine identity stamped onto one ingest."""

    engine: Literal["local_doctr", "tesseract"]
    detection_key: str
    recognition_key: str
    hf_revision: str | None
    image_width: int | None
    image_height: int | None
    image_encoding: str | None = None


class ExchangeExtension(BaseModel):
    """Model runs and the image size needed to assemble upright geometry."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    model_runs: tuple[ModelRun, ...] = ()
    image_width: int | None = None
    image_height: int | None = None


def canonical_json(payload: Mapping[str, str]) -> bytes:
    """Return the canonical UTF-8 JSON for a string map."""
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def image_encoding_of(payload: bytes) -> str:
    """Name the image encoding of the bytes an OCR engine actually received."""
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if payload.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "webp"
    return "unidentified"


def preprocessing_for_engine(
    engine: Literal["local_doctr", "tesseract"],
    *,
    image_encoding: str | None = None,
) -> dict[str, str]:
    """Return the preprocessing contract the named engine actually applies."""
    if engine == "local_doctr":
        return dict(DOCTR_PREPROCESSING)
    encoding = image_encoding if image_encoding else "unidentified"
    return {"image_encoding": encoding, "psm": _TESSERACT_PSM}


def ocr_exchange_identity(
    *,
    engine: Literal["local_doctr", "tesseract"],
    detection_key: str,
    recognition_key: str,
    hf_revision: str | None,
    image_width: int,
    image_height: int,
    image_encoding: str | None = None,
) -> OcrExchangeIdentity:
    """Build the OCR identity a page loader stamps onto one ingest."""
    width = image_width if image_width > 0 else None
    height = image_height if image_height > 0 else None
    return OcrExchangeIdentity(
        engine=engine,
        detection_key=detection_key,
        recognition_key=recognition_key,
        hf_revision=hf_revision,
        image_width=width,
        image_height=height,
        image_encoding=image_encoding,
    )


def _write_json(store: LabelerPageStore, payload: Mapping[str, str]) -> str:
    return store.blobs.write(canonical_json(payload))


def build_ocr_model_run(
    store: LabelerPageStore,
    identity: OcrExchangeIdentity,
    *,
    image_sha256: str,
    output_sha256: str,
) -> ModelRun:
    """Record one OCR run from the configured engine and the blobs it wrote."""
    version = identity.hf_revision or f"{identity.detection_key}+{identity.recognition_key}"
    model_hash = _write_json(
        store,
        {
            "detection_key": identity.detection_key,
            "engine": identity.engine,
            "hf_revision": identity.hf_revision or "",
            "recognition_key": identity.recognition_key,
        },
    )
    config_hash = _write_json(
        store,
        {
            "detection_key": identity.detection_key,
            "hf_revision": identity.hf_revision or "",
            "recognition_key": identity.recognition_key,
            "role": "config",
        },
    )
    preprocessing_hash = _write_json(
        store,
        preprocessing_for_engine(identity.engine, image_encoding=identity.image_encoding),
    )
    return ModelRun(
        run_id=f"{identity.engine}-ocr",
        model_name=identity.engine,
        model_version=version,
        purpose=ModelRunPurpose.OCR,
        input_artifact_sha256=image_sha256,
        output_artifact_sha256=output_sha256,
        model_artifact_sha256=model_hash,
        config_sha256=config_hash,
        preprocessing_sha256=preprocessing_hash,
    )


def build_page_region_model_run(
    store: LabelerPageStore,
    *,
    model_id: str,
    model_version: str,
    depends_on: Sequence[str],
    run_id: str,
    image_sha256: str,
) -> ModelRun:
    """Record one page-region run and the preprocessing facets it read."""
    output_hash = _write_json(
        store,
        {"model_id": model_id, "model_version": model_version, "run_id": run_id},
    )
    model_hash = _write_json(store, {"model_id": model_id, "model_version": model_version})
    config_hash = _write_json(
        store,
        {"model_id": model_id, "model_version": model_version, "role": "config"},
    )
    preprocessing_hash = _write_json(store, {"depends_on": ",".join(sorted(depends_on))})
    return ModelRun(
        run_id=run_id,
        model_name=model_id,
        model_version=model_version,
        purpose=ModelRunPurpose.PAGE_REGION,
        input_artifact_sha256=image_sha256,
        output_artifact_sha256=output_hash,
        model_artifact_sha256=model_hash,
        config_sha256=config_hash,
        preprocessing_sha256=preprocessing_hash,
    )


def exchange_of(aggregate: PageAggregate) -> ExchangeExtension:
    """Return the stored exchange extension, or an empty one."""
    raw = aggregate.record.extensions.get(EXCHANGE_NAMESPACE)
    if not raw:
        return ExchangeExtension()
    try:
        return ExchangeExtension.model_validate(raw)
    except ValidationError as exc:
        raise ValueError("stored exchange model record is invalid") from exc


def merge_exchange_run(
    current: ExchangeExtension,
    run: ModelRun,
    *,
    image_width: int | None,
    image_height: int | None,
) -> ExchangeExtension:
    """Replace any stored run with the same purpose."""
    kept = tuple(item for item in current.model_runs if item.purpose != run.purpose)
    width = image_width if image_width is not None else current.image_width
    height = image_height if image_height is not None else current.image_height
    return ExchangeExtension(model_runs=(*kept, run), image_width=width, image_height=height)


def stamp_exchange(
    aggregate: PageAggregate,
    extension: ExchangeExtension,
    store: LabelerPageStore,
) -> None:
    """Persist *extension* on an already saved page aggregate."""
    aggregate.set_extension(EXCHANGE_NAMESPACE, extension)
    store.save_page(aggregate)


def _ocr_image_hash(aggregate: PageAggregate) -> str | None:
    provenance = aggregate.record.provenance
    if provenance is None:
        return None
    for node in provenance.nodes.values():
        if node.source == "ocr" and len(node.blob_refs) >= 2:
            return node.blob_refs[1]
    return None


def record_page_region_exchange(
    store: LabelerPageStore,
    page_ids: Sequence[UUID],
    *,
    model_id: str,
    model_version: str,
    depends_on: Sequence[str],
    run_id: str,
) -> None:
    """Stamp the page-region model onto each already ingested page.

    A stamp failure is logged and skipped. The proposal run that triggered
    this call is already durable, and losing that run would be worse than
    leaving one page without a model record.
    """
    for page_id in page_ids:
        if page_id == NIL_PAGE_ID:
            continue
        try:
            aggregate = store.get_page(page_id)
        except AggregateNotFoundError:
            log.warning("page-region exchange skipped missing page_id=%s", page_id)
            continue
        except PersistenceError as exc:
            log.warning("page-region exchange skipped page_id=%s: %s", page_id, exc)
            continue
        image_sha256 = _ocr_image_hash(aggregate)
        if image_sha256 is None:
            log.warning("page-region exchange skipped a page with no OCR image page_id=%s", page_id)
            continue
        try:
            run = build_page_region_model_run(
                store,
                model_id=model_id,
                model_version=model_version,
                depends_on=depends_on,
                run_id=run_id,
                image_sha256=image_sha256,
            )
            current = exchange_of(aggregate)
            stamp_exchange(
                aggregate,
                merge_exchange_run(current, run, image_width=None, image_height=None),
                store,
            )
        except (OSError, ValueError, ValidationError, PersistenceError) as exc:
            log.warning("page-region exchange skipped page_id=%s: %s", page_id, exc)


def upright_exchange_geometry(
    *,
    page_id: str,
    page_sha256: str,
    page_head_sha256: str,
    image_sha256: str,
    image_width: int,
    image_height: int,
    ocr_run: ModelRun,
    region_run: ModelRun,
    word_id: str,
    word_revision: int,
    box: tuple[float, float, float, float],
) -> tuple[PageGeometry, tuple[CoordinateTransform, CoordinateTransform], WordGeometry]:
    """Build the upright identity geometry chain for one corrected word.

    The crop stage uses the OCR run's preprocessing hash. Both model runs
    must already name the image and their output blobs.
    """
    if ocr_run.preprocessing_sha256 is None or ocr_run.output_artifact_sha256 is None:
        raise ValueError("OCR model run is missing preprocessing or output")
    if region_run.output_artifact_sha256 is None:
        raise ValueError("page-region model run is missing output")
    x0, y0, x1, y1 = box
    orientation = CoordinateTransform(
        transform_id="orientation-transform",
        stage=CoordinateTransformStage.ORIENTATION,
        source_space="source_pixels",
        target_space="oriented_pixels",
        source_coordinate_space_id="source-v1",
        target_coordinate_space_id="oriented-v1",
        source_orientation=SourceOrientation.UPRIGHT,
        source_artifact_sha256=image_sha256,
        target_artifact_sha256=image_sha256,
        source_width=image_width,
        source_height=image_height,
        target_width=image_width,
        target_height=image_height,
        crop_recipe="identity",
        crop_recipe_version="1",
        padding_px=0,
        resampling="nearest",
        preprocessing_sha256=ocr_run.preprocessing_sha256,
        transform_version="1",
        affine=_IDENTITY_AFFINE,
    )
    crop = CoordinateTransform(
        transform_id="crop-transform",
        stage=CoordinateTransformStage.CROP,
        source_space="oriented_pixels",
        target_space="image_pixels",
        source_coordinate_space_id="oriented-v1",
        target_coordinate_space_id="image-v1",
        source_orientation=SourceOrientation.UPRIGHT,
        source_artifact_sha256=image_sha256,
        target_artifact_sha256=image_sha256,
        source_width=image_width,
        source_height=image_height,
        target_width=image_width,
        target_height=image_height,
        crop_recipe="identity",
        crop_recipe_version="1",
        padding_px=0,
        resampling="nearest",
        preprocessing_sha256=ocr_run.preprocessing_sha256,
        transform_version="1",
        affine=_IDENTITY_AFFINE,
    )
    page_geometry = PageGeometry(
        page_id=page_id,
        page_sha256=page_sha256,
        source_image_artifact_sha256=image_sha256,
        source_image_width=image_width,
        source_image_height=image_height,
        image_artifact_sha256=image_sha256,
        page_head_sha256=page_head_sha256,
        ocr_artifact_sha256=ocr_run.output_artifact_sha256,
        page_region_artifact_sha256=region_run.output_artifact_sha256,
        coordinate_space="image_pixels",
        coordinate_space_id="image-v1",
        source_orientation=SourceOrientation.UPRIGHT,
        transform_ids=(orientation.transform_id, crop.transform_id),
        ocr_model_run_id=ocr_run.run_id,
        page_region_model_run_id=region_run.run_id,
        image_width=image_width,
        image_height=image_height,
    )
    word_geometry = WordGeometry(
        word_id=word_id,
        word_revision=word_revision,
        page_sha256=page_sha256,
        page_head_sha256=page_head_sha256,
        image_artifact_sha256=image_sha256,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        coordinate_space="image_pixels",
        coordinate_space_id="image-v1",
        transform_id=crop.transform_id,
        source_orientation=SourceOrientation.UPRIGHT,
    )
    return page_geometry, (orientation, crop), word_geometry


@dataclass(frozen=True)
class ExchangePart:
    """One correction's portable geometry, runs, and replacement artifacts."""

    page_geometry: PageGeometry | None = None
    geometry: tuple[WordGeometry, ...] | None = None
    model_runs: tuple[ModelRun, ...] = ()
    coordinate_transforms: tuple[CoordinateTransform, ...] = ()
    replacement_artifacts: tuple[ReplacementArtifact, ...] = ()


@dataclass(frozen=True)
class FoldedExchange:
    """History folded so every corrected word keeps its latest box."""

    page_geometry: PageGeometry | None = None
    geometry: tuple[WordGeometry, ...] | None = None
    model_runs: tuple[ModelRun, ...] = ()
    coordinate_transforms: tuple[CoordinateTransform, ...] = ()
    replacement_artifacts: tuple[ReplacementArtifact, ...] = ()


def fold_exchange_history(parts: Sequence[ExchangePart]) -> FoldedExchange:
    """Merge correction history for one validation or one export.

    Page geometry stays only when every part has it. Word boxes are the
    latest box per word. A last part whose page and word geometry disagree
    is left unchanged so the bundle constructor rejects that pair.
    """
    artifacts: dict[str, ReplacementArtifact] = {}
    runs: dict[str, ModelRun] = {}
    transforms: dict[str, CoordinateTransform] = {}
    for part in parts:
        for artifact in part.replacement_artifacts:
            previous = artifacts.setdefault(artifact.artifact_id, artifact)
            if previous != artifact:
                raise ValueError("conflicting replacement artifact provenance")
        for run in part.model_runs:
            runs[run.run_id] = run
        for transform in part.coordinate_transforms:
            transforms[transform.transform_id] = transform
    latest = parts[-1] if parts else None
    page_geometry = None if latest is None else latest.page_geometry
    geometry = None if latest is None else latest.geometry
    pair_disagrees = latest is not None and (page_geometry is None) != (geometry is None)
    history_incomplete = any(part.page_geometry is None for part in parts)
    if latest is not None and not pair_disagrees and not history_incomplete:
        boxes: dict[str, WordGeometry] = {}
        for part in parts:
            if part.geometry is None:
                continue
            for box in part.geometry:
                boxes[box.word_id] = box
        geometry = tuple(boxes.values()) if boxes else None
    elif not pair_disagrees:
        page_geometry = None
        geometry = None
    return FoldedExchange(
        page_geometry=page_geometry,
        geometry=geometry,
        model_runs=tuple(runs.values()),
        coordinate_transforms=tuple(transforms.values()),
        replacement_artifacts=tuple(artifacts.values()),
    )


def recorded_run_artifacts(
    store: LabelerPageStore,
    page_id: UUID,
) -> tuple[tuple[ModelRun, ...], tuple[tuple[ReplacementArtifact, bytes], ...]]:
    """Copy page-store model-run blobs into replacement artifacts.

    A missing page or an incomplete blob set is skipped. The caller can
    still emit a correction that does not depend on that run.
    """
    try:
        aggregate = store.get_page(page_id)
    except AggregateNotFoundError:
        return (), ()
    try:
        extension = exchange_of(aggregate)
    except ValueError:
        log.warning("recorded model runs skipped an invalid exchange record page_id=%s", page_id)
        return (), ()
    runs: list[ModelRun] = []
    published: list[tuple[ReplacementArtifact, bytes]] = []
    for run in extension.model_runs:
        collected: list[tuple[ReplacementArtifact, bytes]] = []
        complete = True
        hashes = (
            ("input", run.input_artifact_sha256),
            ("output", run.output_artifact_sha256),
            ("model", run.model_artifact_sha256),
            ("config", run.config_sha256),
            ("preprocessing", run.preprocessing_sha256),
        )
        for role, digest in hashes:
            if digest is None:
                continue
            try:
                payload = store.blobs.read(digest)
            except OSError:
                complete = False
                break
            if hashlib.sha256(payload).hexdigest() != digest:
                complete = False
                break
            collected.append(
                (
                    ReplacementArtifact(
                        artifact_id=f"exchange:{run.run_id}:{role}",
                        relative_path=f"{digest}.artifact",
                        sha256=digest,
                        byte_size=len(payload),
                        media_type="application/octet-stream",
                    ),
                    payload,
                )
            )
        if not complete:
            log.warning("recorded model run blobs are incomplete run_id=%s", run.run_id)
            continue
        runs.append(run)
        published.extend(collected)
    return tuple(runs), tuple(published)


def _referenced_exchange_hashes(
    model_runs: Mapping[str, ModelRun],
    page_geometry: PageGeometry | None,
    coordinate_transforms: Sequence[CoordinateTransform],
) -> set[str]:
    referenced: set[str] = set()
    for run in model_runs.values():
        for digest in (
            run.input_artifact_sha256,
            run.output_artifact_sha256,
            run.model_artifact_sha256,
            run.config_sha256,
            run.preprocessing_sha256,
        ):
            if digest is not None:
                referenced.add(digest)
    if page_geometry is not None:
        referenced.update(
            (
                page_geometry.page_sha256,
                page_geometry.source_image_artifact_sha256,
                page_geometry.image_artifact_sha256,
                page_geometry.page_head_sha256,
                page_geometry.ocr_artifact_sha256,
                page_geometry.page_region_artifact_sha256,
            )
        )
    for transform in coordinate_transforms:
        referenced.add(transform.source_artifact_sha256)
        referenced.add(transform.target_artifact_sha256)
        referenced.add(transform.preprocessing_sha256)
    return referenced


def merge_recorded_runs(
    model_runs: dict[str, ModelRun],
    artifacts: dict[str, ReplacementArtifact],
    payloads: dict[str, bytes],
    recorded_runs: Sequence[ModelRun],
    recorded_payloads: Sequence[tuple[ReplacementArtifact, bytes]],
    *,
    page_geometry: PageGeometry | None = None,
    coordinate_transforms: Sequence[CoordinateTransform] = (),
) -> None:
    """Add recorded blobs that a kept run, page geometry, or transform names."""
    for run in recorded_runs:
        model_runs.setdefault(run.run_id, run)
    referenced = _referenced_exchange_hashes(model_runs, page_geometry, coordinate_transforms)
    known_hashes = {artifact.sha256 for artifact in artifacts.values()}
    for artifact, payload in recorded_payloads:
        if artifact.sha256 not in referenced or artifact.sha256 in known_hashes:
            continue
        previous = artifacts.setdefault(artifact.artifact_id, artifact)
        if previous != artifact:
            raise ValueError("conflicting replacement artifact provenance")
        payloads[artifact.sha256] = payload
        known_hashes.add(artifact.sha256)


def build_immutable_correction_bundle(
    *,
    labeling_bundle_id: str,
    configuration_hash: str,
    corrections: Sequence[TypographyCorrection],
    replacement_artifacts: Sequence[ReplacementArtifact],
    page_geometry: PageGeometry | None,
    geometry: Sequence[WordGeometry] | None,
    model_runs: Sequence[ModelRun],
    coordinate_transforms: Sequence[CoordinateTransform],
) -> CorrectionBundle:
    """Build the content-addressed correction bundle the export route writes."""
    return CorrectionBundle(
        schema_version=LABELING_BUNDLE_SCHEMA_VERSION,
        configuration_hash=configuration_hash,
        labeling_bundle_id=labeling_bundle_id,
        corrections=tuple(corrections),
        replacement_artifacts=tuple(replacement_artifacts),
        page_geometry=page_geometry,
        geometry=tuple(geometry) if geometry else None,
        model_runs=tuple(model_runs),
        coordinate_transforms=tuple(coordinate_transforms),
    )


__all__ = [
    "DOCTR_PREPROCESSING",
    "EXCHANGE_NAMESPACE",
    "ExchangeExtension",
    "ExchangePart",
    "FoldedExchange",
    "OcrExchangeIdentity",
    "build_immutable_correction_bundle",
    "build_ocr_model_run",
    "build_page_region_model_run",
    "canonical_json",
    "exchange_of",
    "fold_exchange_history",
    "image_encoding_of",
    "merge_exchange_run",
    "merge_recorded_runs",
    "ocr_exchange_identity",
    "preprocessing_for_engine",
    "record_page_region_exchange",
    "recorded_run_artifacts",
    "stamp_exchange",
    "upright_exchange_geometry",
]
