"""Task 9A checkpoint: pinned bundle intake, model runs, and correction export."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from eventsourcing.persistence import IntegrityError
from pdomain_book_tools.schemas.emit import emit_schema_manifest
from pdomain_book_tools.typography import (
    ConfidenceTier,
    CorrectionBundle,
    CorrectionDecision,
    LabelingBundle,
    LabelSource,
    LabelState,
    ModelRun,
    ModelRunPurpose,
    PageGeometry,
    ReplacementArtifact,
    ReviewState,
    TypographyCorrection,
    TypographySpan,
    WordGeometry,
    WordTypography,
)
from pdomain_ops.page_aggregate import PageAggregate

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import (
    LocalDoctrPageLoader,
    _ingest_ocr_result,
)
from pdomain_ocr_labeler_spa.adapters.ocr.tesseract import TesseractPageLoader
from pdomain_ocr_labeler_spa.api.typography import (
    append_typography_correction,
    export_typography_correction_bundle,
)
from pdomain_ocr_labeler_spa.core.exchange_models import (
    DOCTR_PREPROCESSING,
    ExchangePart,
    build_immutable_correction_bundle,
    build_ocr_model_run,
    canonical_json,
    exchange_of,
    fold_exchange_history,
    image_encoding_of,
    merge_recorded_runs,
    ocr_exchange_identity,
    preprocessing_for_engine,
    record_page_region_exchange,
    recorded_run_artifacts,
    upright_exchange_geometry,
)
from pdomain_ocr_labeler_spa.core.jobs.handlers.propose_regions import handle_propose_regions
from pdomain_ocr_labeler_spa.core.persistence import labeling_contract
from pdomain_ocr_labeler_spa.core.persistence.book_labeling_session import BookLabelingSession
from pdomain_ocr_labeler_spa.core.persistence.labeling_bundle import load_labeling_bundle_directory
from pdomain_ocr_labeler_spa.core.persistence.labeling_contract import (
    LABELING_BUNDLE_SCHEMA_SHA256,
    LABELING_BUNDLE_SCHEMA_VERSION,
)
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.typography_review import (
    TypographyBinding,
    TypographyCorrectionLog,
    TypographyJournalEnvelope,
)
from tests.unit.core.persistence.test_labeling_bundle import _write_bundle


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class _OcrPage:
    def __init__(self, page_id: object) -> None:
        self.page_id = page_id

    def to_dict(self) -> dict[str, object]:
        return {"lines": [], "page_id": str(self.page_id)}


def test_pinned_schema_matches_the_installed_manifest() -> None:
    manifest = emit_schema_manifest()
    assert manifest["schema_version"] == LABELING_BUNDLE_SCHEMA_VERSION
    assert manifest["schema_sha256"] == LABELING_BUNDLE_SCHEMA_SHA256


def test_exchange_modules_do_not_import_source_data() -> None:
    root = Path(__file__).parents[4]
    paths = (
        root / "src/pdomain_ocr_labeler_spa/core/exchange_models.py",
        root / "src/pdomain_ocr_labeler_spa/core/persistence/labeling_contract.py",
        root / "src/pdomain_ocr_labeler_spa/core/persistence/labeling_bundle.py",
        root / "src/pdomain_ocr_labeler_spa/adapters/ocr/local_doctr.py",
        root / "src/pdomain_ocr_labeler_spa/adapters/ocr/tesseract.py",
        root / "src/pdomain_ocr_labeler_spa/core/jobs/handlers/propose_regions.py",
        root / "src/pdomain_ocr_labeler_spa/api/typography.py",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "import pdomain_source_data" not in text
        assert "from pdomain_source_data" not in text


def test_product_paths_record_models_and_emit_the_pinned_bundle() -> None:
    doctr = inspect.getsource(LocalDoctrPageLoader._run_ocr_on_path)
    tesseract = inspect.getsource(TesseractPageLoader.run_ocr)
    regions = inspect.getsource(handle_propose_regions)
    export = inspect.getsource(export_typography_correction_bundle)
    directory_load = inspect.getsource(load_labeling_bundle_directory)
    book_load = inspect.getsource(BookLabelingSession._load_bundle)
    assert "ocr_exchange_identity(" in doctr
    assert 'engine="local_doctr"' in doctr
    assert "exchange_identity=" in doctr
    assert "ocr_exchange_identity(" in tesseract
    assert 'engine="tesseract"' in tesseract
    assert 'detection_key="psm3"' in tesseract
    assert "image_encoding_of(image_bytes)" in tesseract
    assert "_record_exchange_region_runs(" in regions
    assert "build_immutable_correction_bundle(" in export
    assert "fold_exchange_history(" in export
    assert "recorded_run_artifacts(" in export
    assert "fold_exchange_history(" in inspect.getsource(append_typography_correction)
    assert "require_pinned_labeling_bundle(" in directory_load
    assert "require_pinned_labeling_bundle(" in book_load


def test_load_rejects_a_bundle_when_the_pinned_hash_drifts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "bundle"
    _write_bundle(root)
    monkeypatch.setattr(labeling_contract, "LABELING_BUNDLE_SCHEMA_SHA256", "0" * 64)
    labeling_contract._installed_schema_matches_pin.cache_clear()
    try:
        with pytest.raises(ValueError, match="pinned"):
            load_labeling_bundle_directory(root)
    finally:
        labeling_contract._installed_schema_matches_pin.cache_clear()


def _page_head(bundle: LabelingBundle) -> bytes:
    return (
        json.dumps(
            {
                "configuration_hash": bundle.configuration_hash,
                "image_sha256": bundle.image_sha256,
                "page_id": bundle.page_id,
                "page_sha256": bundle.page_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _reviewed_correction(bundle: LabelingBundle) -> tuple[TypographyCorrection, bytes]:
    word = bundle.words[0]
    corrected = "Corrected"
    corrected_bytes = corrected.encode()
    replacement = WordTypography(
        word_id=word.word_id,
        text=corrected,
        text_sha256=_sha(corrected_bytes),
        page_content_sha256=bundle.page_sha256,
        image_artifact_sha256=bundle.image_sha256,
        grapheme_map_version=word.grapheme_map_version,
        taxonomy_version=bundle.taxonomy.version,
        taxonomy_hash=bundle.taxonomy.taxonomy_hash,
        label_states={"italic": LabelState.POSITIVE},
        source_evidence_ids=word.source_evidence_ids,
        word_revision=word.word_revision + 1,
        review_state=ReviewState.REVIEWED,
        spans=(
            TypographySpan(
                span_id="italic-span",
                label="italic",
                start=0,
                end=len(corrected),
                label_source=LabelSource.HUMAN,
                confidence_tier=ConfidenceTier.GOLD,
                alignment_evidence_id=word.source_evidence_ids[0],
            ),
        ),
    )
    correction = TypographyCorrection(
        correction_id="corr-1",
        word_id=word.word_id,
        revision=1,
        supersedes_id=None,
        base_page_sha256=bundle.page_sha256,
        base_image_sha256=bundle.image_sha256,
        base_text_sha256=word.text_sha256,
        base_word_revision=word.word_revision,
        replacement_text_sha256=replacement.text_sha256,
        replacement_page_sha256=bundle.page_sha256,
        replacement_image_sha256=bundle.image_sha256,
        replacement_page_head_sha256=bundle.page_head_sha256,
        replacement_word_revision=replacement.word_revision,
        taxonomy_version=bundle.taxonomy.version,
        taxonomy_hash=bundle.taxonomy.taxonomy_hash,
        grapheme_map_version=word.grapheme_map_version,
        page_head_sha256=bundle.page_head_sha256,
        labeler_id="reviewer",
        decision=CorrectionDecision.APPROVED_EDIT,
        replacement=replacement,
    )
    return correction, corrected_bytes


def _replacement_artifacts(
    store: LabelerPageStore,
    *,
    image_bytes: bytes,
    page_bytes: bytes,
    page_head: bytes,
    corrected_bytes: bytes,
    ocr_run: ModelRun,
    region_run: ModelRun,
) -> tuple[tuple[ReplacementArtifact, bytes], ...]:
    by_hash: dict[str, tuple[str, bytes, str]] = {}

    def add(artifact_id: str, payload: bytes, media: str) -> None:
        by_hash.setdefault(_sha(payload), (artifact_id, payload, media))

    add("image", image_bytes, "image/png")
    add("page", page_bytes, "application/octet-stream")
    add("page-head", page_head, "application/json")
    add("corrected-text", corrected_bytes, "text/plain")
    for run in (ocr_run, region_run):
        for digest in (
            run.output_artifact_sha256,
            run.model_artifact_sha256,
            run.config_sha256,
            run.preprocessing_sha256,
        ):
            assert digest is not None
            add(f"blob-{digest[:12]}", store.blobs.read(digest), "application/json")
    return tuple(
        (
            ReplacementArtifact(
                artifact_id=artifact_id,
                relative_path=f"{digest}.artifact",
                sha256=digest,
                byte_size=len(payload),
                media_type=media,
            ),
            payload,
        )
        for digest, (artifact_id, payload, media) in sorted(by_hash.items(), key=lambda item: item[1][0])
    )


def _emit_twice(bundle: LabelingBundle, envelope: TypographyJournalEnvelope) -> CorrectionBundle:
    assert bundle.bundle_id is not None
    arguments = {
        "labeling_bundle_id": bundle.bundle_id,
        "configuration_hash": bundle.configuration_hash,
        "corrections": (envelope.correction,),
        "replacement_artifacts": envelope.replacement_artifacts,
        "page_geometry": envelope.page_geometry,
        "geometry": envelope.geometry,
        "model_runs": envelope.model_runs,
        "coordinate_transforms": envelope.coordinate_transforms,
    }
    first = build_immutable_correction_bundle(**arguments)
    second = build_immutable_correction_bundle(**arguments)
    assert first.model_dump_json() == second.model_dump_json()
    assert first.bundle_id == second.bundle_id
    return first


def _reloaded_model_runs(
    project_dir: Path, image_bytes: bytes
) -> tuple[LabelerPageStore, ModelRun, ModelRun, UUID]:
    page_id = uuid4()
    store = LabelerPageStore(project_dir)
    _ingest_ocr_result(
        page=_OcrPage(page_id),
        image_bytes=image_bytes,
        page_index=0,
        store=store,
        exchange_identity=ocr_exchange_identity(
            engine="local_doctr",
            detection_key="db_resnet50",
            recognition_key="crnn_vgg16_bn",
            hf_revision="rev-2026-08-21",
            image_width=120,
            image_height=240,
        ),
    )
    record_page_region_exchange(
        store,
        (page_id,),
        model_id="null-detector",
        model_version="0.0.0",
        depends_on=("words", "lines"),
        run_id="region-run-1",
    )
    store.close()
    reopened = LabelerPageStore(project_dir)
    extension = exchange_of(reopened.get_page(page_id))
    runs = {run.purpose: run for run in extension.model_runs}
    ocr_run = runs[ModelRunPurpose.OCR]
    region_run = runs[ModelRunPurpose.PAGE_REGION]
    assert ocr_run.model_name == "local_doctr"
    assert ocr_run.model_version == "rev-2026-08-21"
    assert region_run.model_name == "null-detector"
    assert region_run.model_version == "0.0.0"
    assert extension.image_width == 120
    assert extension.image_height == 240
    assert ocr_run.preprocessing_sha256 is not None
    assert region_run.preprocessing_sha256 is not None
    assert reopened.blobs.read(ocr_run.preprocessing_sha256) == canonical_json(DOCTR_PREPROCESSING)
    assert reopened.blobs.read(region_run.preprocessing_sha256) == canonical_json(
        {"depends_on": "lines,words"}
    )
    return reopened, ocr_run, region_run, page_id


def test_geometry_optional_bundle_reloads_review_and_emits_one_bundle(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    written = _write_bundle(root)
    with load_labeling_bundle_directory(root) as loaded:
        bundle = loaded.bundle
        assert bundle == written
        assert bundle.page_geometry is None
        assert bundle.geometry is None
        assert bundle.schema_version == LABELING_BUNDLE_SCHEMA_VERSION

    image_bytes = b"png"
    page_bytes = b"page-record"
    page_head = _page_head(bundle)
    assert _sha(image_bytes) == bundle.image_sha256
    assert _sha(page_bytes) == bundle.page_sha256
    assert _sha(page_head) == bundle.page_head_sha256
    reopened, ocr_run, region_run, _page_id = _reloaded_model_runs(tmp_path / "project", image_bytes)
    word = bundle.words[0]
    correction, corrected_bytes = _reviewed_correction(bundle)
    page_geometry, transforms, word_geometry = upright_exchange_geometry(
        page_id=bundle.page_id,
        page_sha256=bundle.page_sha256,
        page_head_sha256=bundle.page_head_sha256,
        image_sha256=bundle.image_sha256,
        image_width=120,
        image_height=240,
        ocr_run=ocr_run,
        region_run=region_run,
        word_id=word.word_id,
        word_revision=word.word_revision + 1,
        box=(4.0, 8.0, 40.0, 30.0),
    )
    published = _replacement_artifacts(
        reopened,
        image_bytes=image_bytes,
        page_bytes=page_bytes,
        page_head=page_head,
        corrected_bytes=corrected_bytes,
        ocr_run=ocr_run,
        region_run=region_run,
    )
    project_root = tmp_path / "project"
    log = TypographyCorrectionLog(project_root, corpus_root=tmp_path)
    log.append(
        correction,
        logical_page_id=bundle.page_id,
        current=TypographyBinding(
            page_sha256=bundle.page_sha256,
            image_sha256=bundle.image_sha256,
            text_sha256=word.text_sha256,
            page_head_sha256=bundle.page_head_sha256,
            word_revision=word.word_revision,
        ),
        replacement_artifacts=tuple(artifact for artifact, _payload in published),
        page_geometry=page_geometry,
        geometry=(word_geometry,),
        model_runs=(ocr_run, region_run),
        coordinate_transforms=transforms,
        artifact_payloads=published,
    )
    reloaded = TypographyCorrectionLog(project_root, corpus_root=tmp_path).records(bundle.page_id)
    assert len(reloaded) == 1
    envelope = reloaded[0]
    assert envelope.correction == correction
    assert envelope.page_geometry == page_geometry
    assert envelope.geometry == (word_geometry,)
    assert envelope.model_runs == (ocr_run, region_run)
    assert envelope.coordinate_transforms == transforms
    emitted = _emit_twice(bundle, envelope)
    assert emitted.bundle_id is not None
    assert len(emitted.bundle_id) == 64
    emitted.validate_against(bundle)
    reopened.close()


def test_fold_keeps_the_latest_box_for_every_corrected_word() -> None:
    first_page = PageGeometry.model_construct()
    second_page = PageGeometry.model_construct()
    first_box = WordGeometry.model_construct(word_id="word-a", word_revision=1)
    second_box = WordGeometry.model_construct(word_id="word-b", word_revision=1)
    updated = WordGeometry.model_construct(word_id="word-a", word_revision=2)
    folded = fold_exchange_history(
        (
            ExchangePart(page_geometry=first_page, geometry=(first_box,)),
            ExchangePart(page_geometry=second_page, geometry=(second_box, updated)),
        )
    )
    assert folded.page_geometry is second_page
    assert folded.geometry is not None
    assert [(item.word_id, item.word_revision) for item in folded.geometry] == [
        ("word-a", 2),
        ("word-b", 1),
    ]


def test_fold_omits_geometry_when_any_correction_lacks_it() -> None:
    page = PageGeometry.model_construct()
    box = WordGeometry.model_construct(word_id="word-a", word_revision=1)
    folded = fold_exchange_history(
        (
            ExchangePart(page_geometry=None, geometry=None),
            ExchangePart(page_geometry=page, geometry=(box,)),
        )
    )
    assert folded.page_geometry is None
    assert folded.geometry is None


def test_fold_keeps_a_disagreement_for_the_bundle_constructor() -> None:
    box = WordGeometry.model_construct(word_id="word-a", word_revision=1)
    folded = fold_exchange_history((ExchangePart(page_geometry=None, geometry=(box,)),))
    assert folded.page_geometry is None
    assert folded.geometry == (box,)


def test_recorded_runs_emit_without_a_journal_copy(tmp_path: Path) -> None:
    store, ocr_run, region_run, page_id = _reloaded_model_runs(tmp_path / "project", b"png")
    try:
        runs, payloads = recorded_run_artifacts(store, page_id)
        model_runs = {run.run_id: run for run in runs}
        artifacts: dict[str, ReplacementArtifact] = {}
        held: dict[str, bytes] = {}
        merge_recorded_runs(model_runs, artifacts, held, runs, payloads)
        bundle = build_immutable_correction_bundle(
            labeling_bundle_id="0" * 64,
            configuration_hash="0" * 64,
            corrections=(),
            replacement_artifacts=tuple(artifacts.values()),
            page_geometry=None,
            geometry=None,
            model_runs=tuple(model_runs.values()),
            coordinate_transforms=(),
        )
    finally:
        store.close()
    assert {run.run_id for run in bundle.model_runs} == {ocr_run.run_id, region_run.run_id}
    assert ocr_run.preprocessing_sha256 in held
    assert bundle.bundle_id is not None


def test_tesseract_preprocessing_names_the_bytes_that_were_sent(tmp_path: Path) -> None:
    assert image_encoding_of(b"\xff\xd8\xff\xd9") == "jpeg"
    assert image_encoding_of(b"\x89PNG\r\n\x1a\n") == "png"
    store = LabelerPageStore(tmp_path)
    try:
        run = build_ocr_model_run(
            store,
            ocr_exchange_identity(
                engine="tesseract",
                detection_key="psm3",
                recognition_key="eng",
                hf_revision=None,
                image_width=8,
                image_height=8,
                image_encoding=image_encoding_of(b"\xff\xd8\xff\xd9"),
            ),
            image_sha256="a" * 64,
            output_sha256="b" * 64,
        )
        assert run.preprocessing_sha256 is not None
        recorded = store.blobs.read(run.preprocessing_sha256)
    finally:
        store.close()
    assert recorded == canonical_json(preprocessing_for_engine("tesseract", image_encoding="jpeg"))
    assert b"png" not in recorded


def test_model_run_failure_does_not_save_a_page_without_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LabelerPageStore(tmp_path)
    calls: list[int] = []
    real_save = store.save_page

    def save_page(aggregate: PageAggregate) -> None:
        calls.append(1)
        real_save(aggregate)

    monkeypatch.setattr(store, "save_page", save_page)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise ValueError("stamp failed")

    monkeypatch.setattr(
        "pdomain_ocr_labeler_spa.adapters.ocr.local_doctr.build_ocr_model_run",
        explode,
    )
    try:
        with pytest.raises(ValueError, match="stamp failed"):
            _ingest_ocr_result(
                page=_OcrPage(uuid4()),
                image_bytes=b"png",
                page_index=0,
                store=store,
                exchange_identity=ocr_exchange_identity(
                    engine="local_doctr",
                    detection_key="db_resnet50",
                    recognition_key="crnn_vgg16_bn",
                    hf_revision=None,
                    image_width=8,
                    image_height=8,
                ),
            )
    finally:
        store.close()
    assert calls == []


def test_replaced_recorded_run_does_not_attach_unreferenced_blobs() -> None:
    kept = ModelRun(
        run_id="local_doctr-ocr",
        model_name="local_doctr",
        model_version="old",
        purpose=ModelRunPurpose.OCR,
        input_artifact_sha256="1" * 64,
        output_artifact_sha256="2" * 64,
        model_artifact_sha256="3" * 64,
        config_sha256="4" * 64,
        preprocessing_sha256="5" * 64,
    )
    preprocessing = ReplacementArtifact(
        artifact_id="exchange:local_doctr-ocr:preprocessing",
        relative_path=f"{'5' * 64}.artifact",
        sha256="5" * 64,
        byte_size=4,
        media_type="application/octet-stream",
    )
    replaced = ReplacementArtifact(
        artifact_id="exchange:local_doctr-ocr:output",
        relative_path=f"{'6' * 64}.artifact",
        sha256="6" * 64,
        byte_size=3,
        media_type="application/octet-stream",
    )
    model_runs = {kept.run_id: kept}
    artifacts: dict[str, ReplacementArtifact] = {}
    payloads: dict[str, bytes] = {}
    merge_recorded_runs(
        model_runs,
        artifacts,
        payloads,
        (
            ModelRun(
                run_id="local_doctr-ocr",
                model_name="local_doctr",
                model_version="new",
                purpose=ModelRunPurpose.OCR,
                output_artifact_sha256="6" * 64,
                preprocessing_sha256="5" * 64,
            ),
        ),
        ((preprocessing, b"prep"), (replaced, b"new")),
    )
    assert model_runs["local_doctr-ocr"] is kept
    assert list(artifacts) == [preprocessing.artifact_id]
    assert payloads == {"5" * 64: b"prep"}


def test_region_stamp_continues_after_a_persistence_conflict(tmp_path: Path) -> None:
    store = LabelerPageStore(tmp_path)
    page_id = uuid4()

    def boom(_page_id: object) -> None:
        raise IntegrityError("conflict")

    store.get_page = boom
    try:
        record_page_region_exchange(
            store,
            (page_id,),
            model_id="null-detector",
            model_version="0.0.0",
            depends_on=("words",),
            run_id="region-run-1",
        )
    finally:
        store.close()
