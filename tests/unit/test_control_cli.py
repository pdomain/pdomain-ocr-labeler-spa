from __future__ import annotations

import httpx
import pytest

from pdomain_ocr_labeler_spa.control_cli import ControlClient, ControlError, build_request, parse_options


def test_route_mapping_and_preparation_key() -> None:
    options = parse_options(["prepare", "project", "--page", "008.png", "--request-id", "r1"])
    request = build_request(options)
    assert request.method == "POST"
    assert request.path == "/api/pgdp/prepare"
    assert request.body == {"project_id": "project", "page_keys": ["008.png"], "request_id": "r1"}
    view = build_request(
        parse_options(
            [
                "view",
                "--viewer-id",
                "v",
                "--project",
                "p",
                "--page-index",
                "1",
                "--panel",
                "source_alignment",
                "--alignment-id",
                "a",
                "--alignment-group-id",
                "g",
            ]
        )
    )
    assert isinstance(view.body, dict)
    selection = view.body["selection"]
    assert isinstance(selection, dict) and selection["alignment_group_id"] == "g"


def test_job_errors_and_no_unsafe_post_retry() -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("uncertain response")
        return httpx.Response(200, json={"id": "j", "status": "error", "error_message": "failed"})

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handle)) as http:
        client = ControlClient(http)
        with pytest.raises(ControlError, match="failed"):
            _ = client.wait_job("j", timeout=1)
        with pytest.raises(ControlError, match="uncertain"):
            _ = client.request("POST", "/api/pgdp/prepare", {})
    assert calls == ["GET", "POST"]


def test_job_wait_timeout_is_bounded() -> None:
    with (
        httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"id": "j", "status": "running"})
            ),
        ) as http,
        pytest.raises(ControlError, match="timed out"),
    ):
        _ = ControlClient(http).wait_job("j", timeout=0.01)


def test_invalid_cli_arguments_are_structured(capsys: pytest.CaptureFixture[str]) -> None:
    from pdomain_ocr_labeler_spa.control_cli import main

    assert main(["unknown-command"]) == 1
    assert "invalid_arguments" in capsys.readouterr().out


def test_page_wait_follows_authoritative_load_job() -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/jobs/j":
            return httpx.Response(200, json={"id": "j", "status": "complete"})
        if len(calls) == 1:
            return httpx.Response(200, json={"page_load_job_id": "j", "generation": 0})
        return httpx.Response(200, json={"page_load_job_id": None, "generation": 1})

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handle)) as http:
        result = ControlClient(http).execute(parse_options(["page", "p", "0", "--wait"]))
    assert isinstance(result, dict) and result["generation"] == 1
    assert calls == ["/api/projects/p/pages/0", "/api/jobs/j", "/api/projects/p/pages/0"]


def test_group_cli_uses_canonical_result_and_decision_fields() -> None:
    request = build_request(
        parse_options(
            ["review-group", "p", "0", "g", "--result-id", "a", "--decision", "pending", "--generation", "2"]
        )
    )
    assert request.body == {"result_id": "a", "expected_generation": 2, "decision": "pending"}


def test_default_catalog_omits_empty_query() -> None:
    request = build_request(parse_options(["catalog"]))
    assert request.params == {"limit": 25, "offset": 0}
    filtered = build_request(parse_options(["catalog", "--query", "Poems"]))
    assert filtered.params is not None
    assert filtered.params["query"] == "Poems"
