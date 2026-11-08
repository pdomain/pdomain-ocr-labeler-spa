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
