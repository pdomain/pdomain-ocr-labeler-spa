from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.responses import JSONResponse

from pdomain_ocr_labeler_spa.api.automation_publication import install_change_publication
from pdomain_ocr_labeler_spa.core.automation.events import AutomationBroker
from pdomain_ocr_labeler_spa.core.project_state import ProjectState


class Result(BaseModel):
    value: str


def test_domain_publication_is_inside_successful_endpoint_boundary() -> None:
    app = FastAPI()
    broker = AutomationBroker()
    state = ProjectState()

    @app.post("/api/projects/load", response_model=Result)
    def mutate() -> Result:
        assert broker.revision == 0
        return Result(value="loaded")

    @app.post("/api/projects/fail", response_model=Result)
    def fail() -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "conflict"})

    install_change_publication(app, broker=broker, project_state=state)
    with TestClient(app) as client:
        assert client.post("/api/projects/load").status_code == 200
        assert broker.revision == 1
        assert broker.history[-1].kind == "project_changed"
        assert client.post("/api/projects/fail").status_code == 409
        assert broker.revision == 1


def test_explicit_page_load_publishes_generation_reset_only_after_success() -> None:
    app = FastAPI()
    broker = AutomationBroker()
    state = ProjectState()

    @app.post("/api/projects/{project_id}/pages/{page_index}/load", response_model=Result)
    def load(project_id: str, page_index: int) -> Result:
        return Result(value=f"loaded:{project_id}:{page_index}")

    @app.post("/api/projects/{project_id}/pages/{page_index}/selection", response_model=Result)
    def edit(project_id: str, page_index: int) -> Result:
        return Result(value=f"edited:{project_id}:{page_index}")

    install_change_publication(app, broker=broker, project_state=state)
    with TestClient(app) as client:
        loaded = client.post("/api/projects/book/pages/2/load")
        assert loaded.status_code == 200, loaded.text
        reset_event = broker.history[-1]
        assert reset_event.kind == "page_changed"
        assert reset_event.page_index == 2
        assert reset_event.generation_reset is True

        edited = client.post("/api/projects/book/pages/2/selection")
        assert edited.status_code == 200, edited.text
        assert broker.history[-1].generation_reset is None


def test_failed_explicit_page_load_publishes_no_event() -> None:
    app = FastAPI()
    broker = AutomationBroker()
    state = ProjectState()

    @app.post("/api/projects/{project_id}/pages/{page_index}/load", response_model=Result)
    def failed_load(project_id: str, page_index: int) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": "load_failed"})

    install_change_publication(app, broker=broker, project_state=state)
    with TestClient(app) as client:
        failed = client.post("/api/projects/book/pages/2/load")
        assert failed.status_code == 422
        assert broker.revision == 0
