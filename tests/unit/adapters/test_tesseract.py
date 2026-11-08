from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from pdomain_book_tools.ocr.page import Page

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import LocalDoctrPageLoader
from pdomain_ocr_labeler_spa.adapters.ocr.page_loader_factory import build_page_loader
from pdomain_ocr_labeler_spa.adapters.ocr.tesseract import (
    OCRCancelledError,
    TesseractCapabilityError,
    TesseractPageLoader,
    _execute,
    parse_tesseract_tsv,
    tesseract_capability,
)
from pdomain_ocr_labeler_spa.core.app_state import build_app_state
from pdomain_ocr_labeler_spa.core.automation.service import AutomationService
from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.handlers.auto_rotate_all import _build_ocr_fn
from pdomain_ocr_labeler_spa.core.jobs.handlers.reload_ocr import _get_page_loader
from pdomain_ocr_labeler_spa.core.jobs.handlers.rotate import handle_rotate_page
from pdomain_ocr_labeler_spa.core.jobs.runner import JobRunner
from pdomain_ocr_labeler_spa.core.models import Project
from pdomain_ocr_labeler_spa.core.notifications import NotificationQueue
from pdomain_ocr_labeler_spa.core.ocr.predictor import PredictorCache
from pdomain_ocr_labeler_spa.core.ocr_config_state import OCRConfigCarrier
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.project_state import ProjectState
from pdomain_ocr_labeler_spa.settings import Settings

TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    "1\t1\t0\t0\t0\t0\t0\t0\t300\t400\t-1\t\n"
    "5\t1\t1\t1\t1\t1\t150\t20\t35\t14\t97.5\tRight\n"
    "5\t1\t1\t1\t1\t2\t200\t20\t30\t14\t88\tcolumn\n"
    "5\t1\t2\t1\t1\t1\t10\t10\t30\t14\t92\tLeft\n"
)


def _project(image: Path) -> Project:
    return Project(
        project_id="test",
        project_root=image.parent,
        image_paths=[image],
        total_pages=1,
        ground_truth_map={image.name: "Never inject this text"},
    )


def test_tsv_preserves_native_blocks_words_boxes_and_confidence() -> None:
    page = parse_tesseract_tsv(TSV, width=300, height=400, page_index=2, name="scan.png")
    assert [word.text for line in page.lines for word in line.words] == ["Right", "column", "Left"]
    assert page.page_index == 2
    assert page.lines[0].words[0].bounding_box.top_left.x == 150
    assert page.lines[0].words[0].ocr_confidence == 0.975
    assert all(not word.ground_truth_text for line in page.lines for word in line.words)
    restored = Page.from_dict(page.to_dict())
    assert [word.text for line in restored.lines for word in line.words] == ["Right", "column", "Left"]


def test_empty_tsv_is_valid_empty_ocr() -> None:
    page = parse_tesseract_tsv(TSV.splitlines()[0], width=300, height=400, page_index=0, name="empty")
    assert not page.lines


def test_malformed_tsv_is_rejected() -> None:
    with pytest.raises(ValueError, match="TSV"):
        parse_tesseract_tsv("text\nhello", width=1, height=1, page_index=0, name="bad")


def test_missing_binary_reports_capability_error() -> None:
    capability = tesseract_capability(binary="pdomain-missing-tesseract")
    assert not capability.available
    assert "binary" in capability.message


def test_missing_language_is_not_silently_replaced() -> None:
    capability = tesseract_capability(language="pdomain_missing_language")
    assert not capability.available
    assert "language" in capability.message


def test_cancelled_loader_does_not_launch_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_process(*args: object, **kwargs: object) -> None:
        pytest.fail("cancelled OCR started a process")

    monkeypatch.setattr(subprocess, "Popen", unexpected_process)
    loader = TesseractPageLoader(project=_project(tmp_path / "scan.png"), cancelled=lambda: True)
    with pytest.raises(OCRCancelledError):
        loader.run_ocr(0)


def test_loader_missing_binary_is_explicit(tmp_path: Path) -> None:
    loader = TesseractPageLoader(project=_project(tmp_path / "scan.png"), binary="pdomain-missing-tesseract")
    with pytest.raises(TesseractCapabilityError, match="binary"):
        loader.run_ocr(0)


@pytest.mark.skipif(not os.environ.get("PDOMAIN_TEST_TESSERACT_SCAN"), reason="real scan not selected")
def test_actual_selected_scan_ocr_without_ground_truth_injection(tmp_path: Path) -> None:
    path = Path(os.environ["PDOMAIN_TEST_TESSERACT_SCAN"])
    (tmp_path / ".nobackup").touch()
    store = LabelerPageStore(project_dir=tmp_path)
    descriptor = os.open(path, os.O_RDONLY)
    try:
        loader = TesseractPageLoader(
            project=_project(path.with_name("nonexistent.png")),
            timeout_s=30,
            store=store,
            image_path_resolver=lambda _: Path(f"/proc/self/fd/{descriptor}"),
        )
        outcome = loader.run_ocr(0)
        assert isinstance(outcome.payload, Page)
        aggregate = store.get_page(outcome.payload.page_id)
        provenance = aggregate.record.provenance
        assert provenance is not None
        assert provenance.nodes[provenance.head_id].tool == "tesseract"
        restored = loader.load_labeled(0)
        assert restored is not None
        assert isinstance(restored.payload, Page)
        assert restored.payload.page_id == outcome.payload.page_id
    finally:
        os.close(descriptor)
        store.close()
    assert isinstance(outcome.payload, Page)
    words = [word for line in outcome.payload.lines for word in line.words]
    assert len(words) > 20
    assert all(not word.ground_truth_text for word in words)
    assert outcome.payload.width > 500


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_and_cancel_reap_owned_process(tmp_path: Path, cancel: bool) -> None:
    (tmp_path / ".nobackup").touch()
    pid_file = tmp_path / "child.pid"
    script = (
        f"import os,time,pathlib; pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(10)"
    )
    started = time.monotonic()
    with pytest.raises(OCRCancelledError if cancel else TimeoutError):
        asyncio.run(
            _execute(
                [sys.executable, "-c", script],
                timeout_s=2 if cancel else 0.2,
                cancelled=(lambda: time.monotonic() - started > 0.2) if cancel else None,
            )
        )
    assert time.monotonic() - started < 2
    child_pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_factory_tesseract_requires_no_doctr_context(tmp_path: Path) -> None:
    settings = Settings(ocr_engine="tesseract")
    loader = build_page_loader(
        project=_project(tmp_path / "scan.png"), settings=settings, context={}, store=None
    )
    assert isinstance(loader, TesseractPageLoader)
    assert build_app_state(settings).ocr_engine.__class__.__name__ == "TesseractOCR"


def test_factory_default_and_explicit_override(tmp_path: Path) -> None:
    settings = Settings()
    project = _project(tmp_path / "scan.png")
    loader = build_page_loader(
        project=project,
        settings=settings,
        context={"predictor_cache": PredictorCache(), "ocr_config_carrier": OCRConfigCarrier()},
        store=None,
    )
    assert isinstance(loader, LocalDoctrPageLoader)
    override_loader = build_page_loader(
        project=project, settings=settings, context={}, store=None, engine="tesseract"
    )
    assert isinstance(override_loader, TesseractPageLoader)


@pytest.mark.parametrize("switch_during_ocr", [False, True])
def test_project_switch_prevents_ocr_store_contamination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    switch_during_ocr: bool,
) -> None:
    (tmp_path / ".nobackup").touch()
    project_a = _project(tmp_path / "a.png").model_copy(update={"project_id": "a"})
    project_b = _project(tmp_path / "b.png").model_copy(update={"project_id": "b"})
    state = ProjectState()
    state.set_loaded_project(project_a)
    store_a = LabelerPageStore(project_dir=tmp_path / "a")
    store_b = LabelerPageStore(project_dir=tmp_path / "b")
    runner = JobRunner(JobEventBroker(), context={"project_state": state, "page_store": store_a})
    automation = AutomationService(project_state=state, runner=runner)
    runner.context["automation"] = automation
    job_id = runner.submit("reload_ocr", project_id="a", payload={"page_index": 0})

    def switch_project() -> None:
        with automation.broker.transaction(), state.mutation_lock:
            state.set_loaded_project(project_b)
            runner.context["page_store"] = store_b

    def recognize(*args: object, **kwargs: object) -> Page:
        switch_project()
        return parse_tesseract_tsv(TSV, width=300, height=400, page_index=0, name="a.png")

    monkeypatch.setattr("pdomain_ocr_labeler_spa.adapters.ocr.tesseract._recognize", recognize)
    settings = Settings(ocr_engine="tesseract")
    try:
        if switch_during_ocr:
            loader = _get_page_loader(runner, state, settings, job_id=job_id, page_index=0)
            with pytest.raises(RuntimeError, match=r"project.*changed"):
                loader.run_ocr(0, edited_image_bytes=b"verified source")
        else:
            switch_project()
            with pytest.raises(RuntimeError, match=r"project.*changed"):
                _get_page_loader(runner, state, settings, job_id=job_id, page_index=0)
        assert state.loaded_project is project_b
        assert not any(path.is_file() for path in (tmp_path / "a" / ".pd-pages" / "blobs").rglob("*"))
        assert not any(path.is_file() for path in (tmp_path / "b" / ".pd-pages" / "blobs").rglob("*"))
    finally:
        store_a.close()
        store_b.close()


def test_tesseract_auto_rotation_rejected_before_predictor_build(tmp_path: Path) -> None:
    state = ProjectState()
    state.set_loaded_project(_project(tmp_path / "scan.png"))
    runner = JobRunner(JobEventBroker())
    with pytest.raises(TesseractCapabilityError, match="unsupported_engine"):
        _build_ocr_fn(runner, state, Settings(ocr_engine="tesseract"))


def test_manual_rotation_cancellation_reaches_provider_before_store_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import Image

    (tmp_path / ".nobackup").touch()
    image_path = tmp_path / "scan.png"
    Image.new("RGB", (100, 200), "white").save(image_path)
    project = _project(image_path)
    state = ProjectState()
    state.set_loaded_project(project)
    store = LabelerPageStore(project_dir=tmp_path)
    runner = JobRunner(
        JobEventBroker(),
        context={
            "project_state": state,
            "page_store": store,
            "settings": Settings(ocr_engine="tesseract"),
            "notification_queue": NotificationQueue(),
        },
    )
    job_id = runner.submit(
        "rotate_page",
        project_id=project.project_id,
        payload={"project_id": project.project_id, "page_index": 0, "degrees": 90},
    )

    def recognize(*args: object, **kwargs: object) -> Page:
        asyncio.run(runner.request_cancel(job_id))
        return parse_tesseract_tsv(TSV, width=300, height=400, page_index=0, name="scan.png")

    monkeypatch.setattr("pdomain_ocr_labeler_spa.adapters.ocr.tesseract._recognize", recognize)
    job = runner.get_job(job_id)
    assert job is not None
    try:
        with pytest.raises(OCRCancelledError):
            asyncio.run(handle_rotate_page(runner, job))
        assert not any(path.is_file() for path in (tmp_path / ".pd-pages" / "blobs").rglob("*"))
        assert state.get_page_state(0) is None
    finally:
        store.close()
