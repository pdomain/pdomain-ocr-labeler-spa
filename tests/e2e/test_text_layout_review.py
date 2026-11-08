"""Exercise real text-layout proposals, correction, persistence and region export."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import pytest
import uvicorn
from pdomain_book_contracts.geometry.bounding_box import BoundingBox
from pdomain_book_contracts.typography import LabelingBundle
from pdomain_book_tools.ocr.page import Page as BookPage
from playwright.sync_api import Page, expect

from pdomain_ocr_labeler_spa.adapters.ocr.local_doctr import _ingest_ocr_result
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.persistence.page_store import LabelerPageStore
from pdomain_ocr_labeler_spa.core.regions.text_layout import TextLayoutDetector
from pdomain_ocr_labeler_spa.settings import Settings
from tests.e2e.helpers import wait_for_project_ready
from tests.fixtures.layout_book import write_layout_bundle
from tests.integration.test_poetry_region_proposal_run import _measure_fn

Case = Literal["verse", "columns", "table", "unresolved"]


@dataclass(frozen=True)
class LayoutServer:
    url: str
    project_id: str
    data_root: Path
    case: Case


def _fixture(root: Path, case: Case) -> BookPage:
    bundle, page = write_layout_bundle(root)
    lines = [" ".join(word.text for word in line.words) for line in page.lines]
    if case != "verse":
        f2_bytes = json.dumps({"image.png": "\n".join(lines)}).encode()
        (root / "artifacts" / "F2.json").write_bytes(f2_bytes)
        digest = hashlib.sha256(f2_bytes).hexdigest()
        bundle = LabelingBundle.model_validate(
            {
                **bundle.model_dump(),
                "bundle_id": None,
                "artifacts": tuple(
                    artifact.model_copy(update={"sha256": digest})
                    if artifact.artifact_id == "f2"
                    else artifact
                    for artifact in bundle.artifacts
                ),
                "evidence": tuple(
                    evidence.model_copy(update={"artifact_sha256": digest}) for evidence in bundle.evidence
                ),
            }
        )
        (root / "labeling-bundle.json").write_text(bundle.model_dump_json(indent=2))
    if case in {"columns", "table"}:
        for index, line in enumerate(page.lines):
            if case == "columns":
                x, y = (20 if index < 2 else 240), 40 + (index % 2) * 50
            else:
                x, y = (20 if index % 2 == 0 else 240), 40 + (index // 2) * 50
            for offset, word in enumerate(line.words):
                word.bounding_box = BoundingBox.from_ltrb(
                    x + offset * 35, y, x + offset * 35 + 30, y + 20, is_normalized=False
                )
    kind = "poetry" if case == "verse" else "column_flow" if case == "columns" else "table_candidate"
    hint = {
        "kind": kind,
        "source": "gutenberg_html",
        "source_ref": "edition/source.html",
        "text": "\n".join(lines),
        "lines": [
            {"text": line, "stanza_index": index // 2, "indent_hint": "2em"}
            for index, line in enumerate(lines)
        ],
        "attributes": [["table_semantics", "data"], ["header_cells", "true"]] if case == "table" else [],
        "table_rows": [lines[:2], lines[2:]] if case in {"table", "unresolved"} else [],
    }
    edition = root / "edition"
    edition.mkdir()
    (edition / "layout-hints.json").write_text(
        json.dumps(
            {
                "schema": "pdomain.edition-layout-hints",
                "version": 1,
                "groups": [
                    {"page_ids": [bundle.page_id], "edition_unit_ids": ["fixture-unit"], "hints": [hint]}
                ],
            }
        )
    )
    return page


@pytest.fixture(params=["verse", "columns", "table", "unresolved"])
def layout_server(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[LayoutServer]:
    case: Case = request.param
    projects = tmp_path / "projects"
    projects.mkdir()
    root = projects / f"layout-{case}"
    book_page = _fixture(root, case)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    settings = Settings(
        host="127.0.0.1",
        port=port,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        source_projects_root=projects,
        no_prefetch=True,
        mode="normal",
    )
    app = build_app(settings)
    app.state.job_runner.context["propose_regions_measure_fn"] = _measure_fn
    app.state.job_runner.context["region_detector"] = TextLayoutDetector()
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    logging.getLogger(__name__).warning("Layout browser server PID=%s URL=%s case=%s", os.getpid(), url, case)
    _record_server(case, url, "started")
    try:
        for _attempt in range(200):
            try:
                if httpx.get(f"{url}/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        loaded = httpx.post(f"{url}/api/projects/load", json={"project_root": str(root)}, timeout=20)
        assert loaded.status_code == 200, loaded.text
        project = app.state.project_state.loaded_project
        assert project is not None
        store = app.state.page_store
        assert isinstance(store, LabelerPageStore)
        _ingest_ocr_result(
            page=book_page,
            image_bytes=(root / "artifacts" / "image.png").read_bytes(),
            page_index=0,
            store=store,
            project=project,
        )
        yield LayoutServer(url, project.project_id, settings.data_root, case)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()
        _record_server(case, url, "stopped")


@pytest.mark.e2e
def test_text_layout_review_in_browser(layout_server: LayoutServer, page: Page) -> None:
    fixture = layout_server
    base = f"{fixture.url}/api/projects/{fixture.project_id}"
    page.goto(f"{fixture.url}/projects/{fixture.project_id}/pages/pageno/1")
    wait_for_project_ready(page)
    expect(page.get_by_test_id("region-page-layout-evidence")).to_be_visible()
    page.get_by_test_id("page-kind-status-button").click()
    page.get_by_test_id("page-kind-select").select_option("body")
    page.get_by_test_id("page-kind-confirm-button").click()
    _propose_regions(page, fixture)
    proposed_payload = httpx.get(f"{base}/pages/0").json()
    proposal = next(
        proposal for proposal in proposed_payload["proposals"] if proposal["evidence"].get("layout_hints")
    )
    _select_region(page, proposal["box"])
    expect(page.get_by_test_id("region-detail")).to_be_visible()
    if fixture.case == "verse":
        expect(page.get_by_test_id("region-layout-editor")).to_be_visible()
        page.get_by_test_id("region-layout-line-0-stanza").fill("2")
        page.get_by_test_id("region-layout-line-0-indent").fill("3em")
    elif fixture.case == "columns":
        payload = httpx.get(f"{base}/pages/0").json()
        proposed = [
            p
            for p in payload["proposals"]
            if p["evidence"].get("layout_structure", {}).get("kind") == "column_flow"
        ]
        assert len(proposed) == 2
        assert {p["role"] for p in proposed} == {"paragraph"}
    elif fixture.case == "table":
        expect(page.get_by_test_id("region-detail-role")).to_have_text("table")
    else:
        expect(page.get_by_test_id("region-detail")).to_contain_text("Unresolved")
    page.get_by_test_id("region-detail-accept").click()
    page.wait_for_function(
        """async base => (await (await fetch(base + '/pages/0')).json()).regions.some(r => r.confirmed)""",
        arg=base,
    )
    payload = httpx.get(f"{base}/pages/0").json()
    confirmed = next(region for region in payload["regions"] if region["confirmed"])
    if fixture.case == "columns":
        _accept_other_column(page, base)
    if fixture.case == "verse":
        assert confirmed["layout_structure"]["lines"][0]["stanza_index"] == 2
        assert confirmed["layout_structure"]["lines"][0]["indent_hint"] == "3em"
    page.reload()
    wait_for_project_ready(page)
    reloaded = httpx.get(f"{base}/pages/0").json()
    assert (
        next(region for region in reloaded["regions"] if region["confirmed"])["layout_structure"]
        == confirmed["layout_structure"]
    )
    _select_region(page, confirmed["box"])
    if fixture.case == "verse":
        _edit_confirmed_verse(page, base)
    page.get_by_test_id("region-layout-export").click()
    expect(page.get_by_test_id("region-layout-export-complete")).to_be_visible(timeout=20000)
    output = fixture.data_root / "doctr-export" / fixture.project_id / "all" / "regions"
    assert (output / "labels.json").is_file()
    _assert_export(output, fixture.case)
    _save_browser_evidence(page, output, fixture.case)


def _assert_export(output: Path, case: Case) -> None:
    if case == "verse":
        structure = json.loads((output / "structure.json").read_text())
        assert structure["regions"][0]["structure"]["lines"][0]["indent_hint"] == "4em"
    elif case == "columns":
        _assert_column_export(output)
    elif case == "table":
        _assert_table_export(output)


def _save_browser_evidence(page: Page, output: Path, case: Case) -> None:
    evidence_path = os.environ.get("PDOMAIN_LAYOUT_EVIDENCE_DIR")
    if evidence_path:
        evidence = Path(evidence_path)
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / ".nobackup").touch()
        page.screenshot(path=str(evidence / f"{case}.png"), full_page=True)
        shutil.copytree(output, evidence / case / "regions", dirs_exist_ok=True)


def _accept_other_column(page: Page, base: str) -> None:
    payload = httpx.get(f"{base}/pages/0").json()
    remaining = next(region for region in payload["regions"] if not region["confirmed"])
    _select_region(page, remaining["box"])
    expect(page.get_by_test_id("region-layout-editor")).to_be_visible()
    page.get_by_test_id("region-detail-accept").click()
    page.wait_for_function(
        """async base => (await (await fetch(base + '/pages/0')).json()).regions
          .filter(r => r.confirmed).length === 2""",
        arg=base,
    )


def _assert_column_export(output: Path) -> None:
    labels = json.loads((output / "labels.json").read_text())
    assert len(labels["pages"][0]["regions"]) == 2
    assert {region["role"] for region in labels["pages"][0]["regions"]} == {"paragraph"}
    structures = json.loads((output / "structure.json").read_text())["regions"]
    assert {entry["structure"]["column_index"] for entry in structures} == {0, 1}
    assert {entry["structure"]["reading_order"] for entry in structures} == {0, 1}
    assert len({entry["structure"]["column_group_id"] for entry in structures}) == 1


def _assert_table_export(output: Path) -> None:
    entries = json.loads((output / "structure.json").read_text())["regions"]
    assert len(entries) == 1 and entries[0]["structure"]["kind"] == "table"
    rows = entries[0]["structure"]["table_rows"]
    assert len(rows) == 2
    assert all(len(row["cells"]) == 2 for row in rows)
    assert all(cell["word_ids"] for row in rows for cell in row["cells"])


def _propose_regions(page: Page, fixture: LayoutServer) -> None:
    page.get_by_test_id("page-actions-compact-overflow").click()
    with page.expect_response(
        f"{fixture.url}/api/projects/{fixture.project_id}/regions/propose"
    ) as submitted:
        page.get_by_test_id("propose-regions-button").click()
    job_id = submitted.value.json()["job_id"]
    events = httpx.get(f"{fixture.url}/api/jobs/{job_id}/events", timeout=20)
    assert "event: complete" in events.text, events.text


def _record_server(case: Case, url: str, event: str) -> None:
    evidence_path = os.environ.get("PDOMAIN_LAYOUT_EVIDENCE_DIR")
    if evidence_path:
        root = Path(evidence_path)
        root.mkdir(parents=True, exist_ok=True)
        (root / ".nobackup").touch()
        with (root / "browser-servers.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps({"pid": os.getpid(), "url": url, "case": case, "event": event}) + "\n")


def _select_region(page: Page, box: dict[str, float]) -> None:
    page.get_by_test_id("rail-target-region").click()
    canvas = page.get_by_test_id("image-viewport").first.locator("canvas").first.bounding_box()
    assert canvas is not None
    scale = canvas["width"] / 400
    page.mouse.click(
        canvas["x"] + (box["x"] + box["width"] / 2) * scale,
        canvas["y"] + (box["y"] + box["height"] / 2) * scale,
    )


def _edit_confirmed_verse(page: Page, base: str) -> None:
    page.get_by_test_id("region-layout-line-0-indent").fill("4em")
    page.get_by_test_id("region-layout-save").click()
    page.wait_for_function(
        """async base => (await (await fetch(base + '/pages/0')).json()).regions.some(
          r => r.confirmed && r.layout_structure?.lines?.[0]?.indent_hint === '4em')""",
        arg=base,
    )
