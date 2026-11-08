from pathlib import Path

from tests.integration.test_region_layout_structure import _prepared_client


def test_viewer_ack_uses_current_ready_page_and_real_word_ids(tmp_path: Path) -> None:
    with _prepared_client(tmp_path) as (client, state, _store, _page, _page_id, _bundle, base):
        assert state.loaded_project is not None
        project_id = state.loaded_project.project_id
        viewer = client.post("/api/automation/viewers", json={}).json()
        payload = client.get(base).json()
        word_id = payload["line_matches"][0]["word_matches"][0]["word_id"]
        request = {
            "viewer_id": viewer["viewer_id"],
            "project_id": project_id,
            "page_index": 0,
            "panel": "selection",
            "selection": {"word_ids": [word_id]},
        }
        response = client.patch("/api/automation/view", json=request)
        assert response.status_code == 200, response.text
        desired = response.json()["desired"]
        observation = {**desired, "generation": payload["generation"], "status": "applied"}
        wrong = {**observation, "selection": {"word_ids": []}}
        assert client.post("/api/automation/view/ack", json=wrong).status_code == 409
        pending = client.get("/api/automation/view", params={"viewer_id": viewer["viewer_id"]}).json()
        assert pending["pending"]
        assert pending["last_observation"]["status"] == "failed"
        current = state.get_page_state(0)
        assert current is not None
        current.generation += 1
        assert client.post("/api/automation/view/ack", json=observation).status_code == 409
        observation["generation"] = current.generation
        accepted = client.post("/api/automation/view/ack", json=observation)
        assert accepted.status_code == 200, accepted.text
        assert not accepted.json()["pending"]


def test_external_mutation_advances_automation_revision_only_after_success(tmp_path: Path) -> None:
    with _prepared_client(tmp_path) as (client, _state, _store, _page, _page_id, _bundle, base):
        before = client.get("/api/automation/state").json()["revision"]
        invalid = client.post(f"{base}/save", json={"generation": -1})
        assert invalid.status_code >= 400
        assert client.get("/api/automation/state").json()["revision"] == before
        saved = client.post(f"{base}/save", json={})
        assert saved.status_code == 200, saved.text
        assert client.get("/api/automation/state").json()["revision"] > before


def test_missing_tesseract_is_a_structured_capability_error(tmp_path: Path) -> None:
    from fastapi import FastAPI

    from pdomain_ocr_labeler_spa.settings import Settings

    with _prepared_client(tmp_path) as (client, _state, _store, _page, _page_id, _bundle, base):
        assert isinstance(client.app, FastAPI)
        settings = client.app.state.settings
        assert isinstance(settings, Settings)
        client.app.state.settings = settings.model_copy(
            update={"tesseract_binary": "/not-installed/tesseract"}
        )
        response = client.post(f"{base}/reload-ocr", json={"engine": "tesseract"})
        assert response.status_code == 503, response.text
        assert response.json()["error"] == "ocr_engine_unavailable"
        assert response.json()["details"]["engine"] == "tesseract"


def test_store_hit_get_and_background_prefetch_publish_readiness(tmp_path: Path) -> None:
    from fastapi import FastAPI

    from pdomain_ocr_labeler_spa.api.pages import _prefetch_with_publication
    from pdomain_ocr_labeler_spa.core.jobs.runner import JobRunner
    from pdomain_ocr_labeler_spa.core.labeler_sidecars import LabelerSidecars, stamp_sidecars_on_page
    from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource

    with _prepared_client(tmp_path) as (client, state, _store, page, _page_id, _bundle, base):
        stored_sidecars = LabelerSidecars(
            char_bboxes_map={"0_0": [{"left": 1, "top": 2, "right": 3, "bottom": 4}]},
            glyph_annotations_map={"0_0": {"reviewed": True}},
        )
        stamp_sidecars_on_page(page, stored_sidecars)
        loads: list[int] = []

        class StoredPageLoader:
            def load_labeled(self, page_index: int) -> PageLoadOutcome:
                loads.append(page_index)
                return PageLoadOutcome(page_index=page_index, source=PageSource.FILESYSTEM, payload=page)

            def load_cached(self, _page_index: int) -> None:
                return None

            def run_ocr(self, _page_index: int, **_kwargs: object) -> PageLoadOutcome:
                raise AssertionError("Stored page must not run OCR")

        assert isinstance(client.app, FastAPI)
        runner = client.app.state.job_runner
        assert isinstance(runner, JobRunner)
        runner.context["page_loader"] = StoredPageLoader()
        current = state.get_page_state(0)
        assert current is not None
        current.page_record = None
        before = client.get("/api/automation/state").json()["revision"]
        response = client.get(base)
        assert response.status_code == 200, response.text
        snapshot = client.get("/api/automation/state").json()
        assert snapshot["revision"] > before
        assert snapshot["pages"][0]["ready"]
        assert current.char_bboxes_map == stored_sidecars.char_bboxes_map
        assert current.glyph_annotations_map == stored_sidecars.glyph_annotations_map
        current.page_record = None
        before = snapshot["revision"]
        assert state.loaded_project is not None
        _prefetch_with_publication(
            state, runner, StoredPageLoader(), 0, expected_project=state.loaded_project
        )
        snapshot = client.get("/api/automation/state").json()
        assert snapshot["revision"] > before
        assert snapshot["pages"][0]["ready"]
        assert current.char_bboxes_map == stored_sidecars.char_bboxes_map
        assert current.glyph_annotations_map == stored_sidecars.glyph_annotations_map
        original = state.loaded_project
        assert original is not None
        load_count = len(loads)
        state.set_loaded_project(original.model_copy(update={"project_id": "other-project"}))
        _prefetch_with_publication(state, runner, StoredPageLoader(), 0, expected_project=original)
        assert len(loads) == load_count
        assert state.get_page_state(0) is None
