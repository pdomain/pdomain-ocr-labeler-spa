"""JSON HTTP control client. Mutating requests are sent exactly once."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Never, final, override
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field, JsonValue, TypeAdapter, ValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence

_JSON = TypeAdapter[JsonValue](JsonValue)
_COMMANDS = (
    "state",
    "catalog",
    "catalog-pages",
    "prepare",
    "load",
    "page",
    "ocr",
    "align",
    "inspect",
    "review-group",
    "view",
    "view-state",
    "propose",
    "proposals",
    "region-review",
    "region-edit",
    "save",
    "reload",
    "export",
    "job",
    "job-wait",
    "cancel",
    "request",
)


@final
class ControlError(RuntimeError):
    def __init__(self, message: str, *, error: str = "client_error", details: JsonValue = None) -> None:
        super().__init__(message)
        self.error = error
        self.details = details

    def envelope(self) -> dict[str, JsonValue]:
        return {"error": self.error, "message": str(self), "details": self.details}


class Options(BaseModel):
    command: str
    arguments: list[str] = Field(default_factory=list)
    base_url: str = "http://127.0.0.1:8000"
    timeout: float = Field(default=30, gt=0, le=3600)
    wait: bool = False
    wait_ack: bool = False
    query: str = ""
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    page: list[str] = Field(default_factory=list)
    page_index: int = Field(default=0, ge=0)
    request_id: str | None = None
    generation: int | None = Field(default=None, ge=0)
    engine: str = "tesseract"
    force: bool = False
    use_edited_image: bool = False
    viewer_id: str | None = None
    project: str | None = None
    panel: str = "selection"
    word_id: list[str] = Field(default_factory=list)
    region_id: str | None = None
    proposal_id: str | None = None
    alignment_id: str | None = None
    alignment_group_id: str | None = None
    disposition: str | None = None
    regions_only: bool = False
    json_body: str | None = None


class JSONArgumentParser(argparse.ArgumentParser):
    @override
    def error(self, message: str) -> Never:
        raise ControlError(message, error="invalid_arguments")


@dataclass(frozen=True)
class RequestSpec:
    method: str
    path: str
    body: JsonValue = None
    params: dict[str, str | int] | None = None


def parse_options(argv: Sequence[str] | None = None) -> Options:
    parser = JSONArgumentParser(prog="pdomain-ocr-labeler-control")
    _ = parser.add_argument("--base-url", default=argparse.SUPPRESS)
    _ = parser.add_argument("--timeout", type=float, default=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in _COMMANDS:
        sub = subparsers.add_parser(name)
        _ = sub.add_argument("arguments", nargs="*")
        _ = sub.add_argument("--base-url", default=argparse.SUPPRESS)
        _ = sub.add_argument("--timeout", type=float, default=argparse.SUPPRESS)
        for flag in ("wait", "wait-ack", "force", "use-edited-image", "regions-only"):
            _ = sub.add_argument("--" + flag, action="store_true")
        for flag in (
            "query",
            "request-id",
            "engine",
            "viewer-id",
            "project",
            "panel",
            "region-id",
            "proposal-id",
            "alignment-id",
            "alignment-group-id",
            "disposition",
        ):
            _ = sub.add_argument("--" + flag, default=argparse.SUPPRESS)
        for flag in ("limit", "offset", "page-index", "generation"):
            _ = sub.add_argument("--" + flag, type=int, default=argparse.SUPPRESS)
        _ = sub.add_argument("--result-id", dest="alignment_id", default=argparse.SUPPRESS)
        _ = sub.add_argument("--decision", dest="disposition", default=argparse.SUPPRESS)
        _ = sub.add_argument("--page", action="append", default=[])
        _ = sub.add_argument("--word-id", action="append", default=[])
        _ = sub.add_argument("--json", dest="json_body")
    return Options.model_validate(vars(parser.parse_args(argv)))


def _argument(options: Options, index: int) -> str:
    if index >= len(options.arguments):
        raise ControlError(
            f"{options.command} requires positional argument {index + 1}", error="invalid_arguments"
        )
    return options.arguments[index]


def build_request(options: Options) -> RequestSpec:
    command = options.command
    extra: dict[str, JsonValue] = {}
    if options.json_body is not None:
        parsed = _JSON.validate_json(options.json_body)
        if not isinstance(parsed, dict):
            raise ControlError("--json must be an object", error="invalid_arguments")
        extra = parsed
    if command == "state":
        return RequestSpec("GET", "/api/automation/state")
    if command == "catalog":
        params: dict[str, str | int] = {"limit": options.limit, "offset": options.offset}
        if options.query:
            params["query"] = options.query
        return RequestSpec(
            "GET",
            "/api/pgdp/projects",
            params=params,
        )
    if command == "catalog-pages":
        return RequestSpec(
            "GET",
            f"/api/pgdp/projects/{quote(_argument(options, 0), safe='')}/pages",
            params={"limit": options.limit, "offset": options.offset},
        )
    if command == "prepare":
        if not options.request_id or not options.page:
            raise ControlError(
                "prepare requires --request-id and at least one --page", error="invalid_arguments"
            )
        return RequestSpec(
            "POST",
            "/api/pgdp/prepare",
            _JSON.validate_python(
                {
                    "project_id": _argument(options, 0),
                    "page_keys": options.page,
                    "request_id": options.request_id,
                }
            ),
        )
    if command == "load":
        return RequestSpec(
            "POST",
            "/api/projects/load",
            {"project_root": _argument(options, 0), "initial_page_index": options.page_index},
        )
    if command in {"view", "view-state"}:
        if not options.viewer_id:
            raise ControlError("view requires --viewer-id", error="invalid_arguments")
        if command == "view-state":
            return RequestSpec("GET", "/api/automation/view", params={"viewer_id": options.viewer_id})
        if not options.project:
            raise ControlError("view requires --project", error="invalid_arguments")
        return RequestSpec(
            "PATCH",
            "/api/automation/view",
            _JSON.validate_python(
                {
                    "viewer_id": options.viewer_id,
                    "project_id": options.project,
                    "page_index": options.page_index,
                    "panel": options.panel,
                    "selection": {
                        "word_ids": options.word_id,
                        "region_id": options.region_id,
                        "proposal_id": options.proposal_id,
                        "alignment_id": options.alignment_id,
                        "alignment_group_id": options.alignment_group_id,
                    },
                }
            ),
        )
    if command in {"job", "job-wait", "cancel"}:
        path = "/api/jobs/" + quote(_argument(options, 0), safe="")
        return RequestSpec(
            "POST" if command == "cancel" else "GET", path + ("/cancel" if command == "cancel" else "")
        )
    if command == "request":
        path = _argument(options, 1)
        if not path.startswith("/api/"):
            raise ControlError("raw request path must start /api/", error="invalid_arguments")
        return RequestSpec(_argument(options, 0).upper(), path, extra if options.json_body else None)
    project = quote(_argument(options, 0), safe="")
    base = f"/api/projects/{project}"
    if command == "propose":
        return RequestSpec("POST", base + "/regions/propose", extra)
    if command == "export":
        return RequestSpec(
            "POST",
            base + "/export",
            {
                "scope": "current",
                "page_index": options.page_index,
                "regions_only": options.regions_only,
                **extra,
            },
        )
    index = _argument(options, 1)
    if not index.isdigit():
        raise ControlError("page index must be a nonnegative integer", error="invalid_arguments")
    page = base + "/pages/" + index
    if command == "page":
        return RequestSpec("GET", page)
    if command == "ocr":
        return RequestSpec(
            "POST",
            page + "/reload-ocr",
            {"engine": options.engine, "force": options.force, "use_edited_image": options.use_edited_image},
        )
    if command == "align":
        if not options.request_id or options.generation is None:
            raise ControlError("align requires --request-id and --generation", error="invalid_arguments")
        return RequestSpec(
            "POST",
            page + "/source-alignment",
            {"request_id": options.request_id, "expected_generation": options.generation},
        )
    if command == "inspect":
        return RequestSpec("GET", page + "/source-alignment")
    if command == "review-group":
        if (
            not options.alignment_id
            or options.generation is None
            or options.disposition not in {"accepted", "edited", "rejected", "pending"}
        ):
            raise ControlError(
                "review-group requires --alignment-id, --generation and --disposition",
                error="invalid_arguments",
            )
        return RequestSpec(
            "PATCH",
            page + "/source-alignment/groups/" + quote(_argument(options, 2), safe=""),
            {
                **extra,
                "result_id": options.alignment_id,
                "expected_generation": options.generation,
                "decision": options.disposition,
            },
        )
    if command == "proposals":
        return RequestSpec("GET", page + "/regions/proposals")
    if command == "region-review":
        action = _argument(options, 3)
        if action not in {"accept", "reject", "unreject"}:
            raise ControlError(
                "region-review action must be accept, reject or unreject", error="invalid_arguments"
            )
        return RequestSpec(
            "POST", page + "/regions/proposals/" + quote(_argument(options, 2), safe="") + "/" + action, extra
        )
    if command == "region-edit":
        return RequestSpec("PATCH", page + "/regions/" + quote(_argument(options, 2), safe=""), extra)
    if command == "save":
        return RequestSpec("POST", page + "/save", {"generation": options.generation})
    if command == "reload":
        return RequestSpec("POST", page + "/load")
    raise ControlError("unsupported command", error="invalid_arguments")


@final
class ControlClient:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def request(
        self, method: str, path: str, body: JsonValue = None, *, params: dict[str, str | int] | None = None
    ) -> JsonValue:
        try:
            response = self.client.request(method, path, json=body, params=params)
        except httpx.HTTPError as exc:
            raise ControlError(
                f"HTTP transport failed; request outcome may be uncertain: {exc}", error="transport_error"
            ) from exc
        try:
            data = _JSON.validate_json(response.content)
        except ValidationError as exc:
            raise ControlError(
                "server returned invalid JSON",
                error="invalid_response",
                details={"status": response.status_code},
            ) from exc
        if response.is_error:
            if isinstance(data, dict):
                message = data.get("message")
                error = data.get("error")
                raise ControlError(
                    message if isinstance(message, str) else "API request failed",
                    error=error if isinstance(error, str) else "http_error",
                    details={
                        "status": response.status_code,
                        "response": data,
                        "request_id": response.headers.get("X-Request-ID"),
                    },
                )
            raise ControlError(
                "API request failed",
                error="http_error",
                details={"status": response.status_code, "response": data},
            )
        return data

    def wait_job(self, job_id: str, *, timeout: float) -> dict[str, JsonValue]:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ControlError(
                    "job wait timed out; job remains authoritative on server",
                    error="wait_timeout",
                    details={"job_id": job_id},
                )
            # Each HTTP poll is bounded by the remaining overall wait budget.
            self.client.timeout = httpx.Timeout(min(remaining, 30))
            result = self.request("GET", "/api/jobs/" + quote(job_id, safe=""))
            if not isinstance(result, dict):
                raise ControlError("job response must be an object", error="invalid_response")
            status = result.get("status")
            if status == "complete":
                return result
            if status in {"error", "cancelled"}:
                message = result.get("error_message")
                raise ControlError(
                    message if isinstance(message, str) else f"job {status}",
                    error="job_" + str(status),
                    details=result,
                )
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))

    def execute(self, options: Options) -> JsonValue:
        spec = build_request(options)
        if options.command == "job-wait":
            return self.wait_job(_argument(options, 0), timeout=options.timeout)
        deadline = time.monotonic() + options.timeout
        result = self.request(spec.method, spec.path, spec.body, params=spec.params)
        if options.wait and isinstance(result, dict):
            job_id = result.get("job_id") or result.get("page_load_job_id")
            if isinstance(job_id, str):
                job = self.wait_job(job_id, timeout=max(0, deadline - time.monotonic()))
                if options.command != "page":
                    return job
                result = self.request("GET", spec.path)
            if options.command == "page" and isinstance(result, dict) and result.get("page_load_error"):
                raise ControlError("page loading failed", error="page_load_error", details=result)
        if options.wait_ack and options.command == "view" and isinstance(result, dict):
            desired = result.get("desired")
            sequence = desired.get("command_seq") if isinstance(desired, dict) else None
            while True:
                if time.monotonic() >= deadline:
                    raise ControlError(
                        "viewer acknowledgement timed out", error="wait_timeout", details=result
                    )
                self.client.timeout = httpx.Timeout(max(0.001, deadline - time.monotonic()))
                result = self.request(
                    "GET", "/api/automation/view", params={"viewer_id": options.viewer_id or ""}
                )
                if not isinstance(result, dict):
                    raise ControlError("viewer response must be an object", error="invalid_response")
                acknowledged = result.get("acknowledged")
                if (
                    not result.get("pending")
                    and isinstance(acknowledged, dict)
                    and acknowledged.get("command_seq") == sequence
                ):
                    return result
                desired = result.get("desired")
                if isinstance(desired, dict) and desired.get("command_seq") != sequence:
                    raise ControlError(
                        "viewer command was superseded", error="viewer_superseded", details=result
                    )
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        options = parse_options(argv)
        with httpx.Client(base_url=options.base_url.rstrip("/"), timeout=options.timeout) as client:
            result = ControlClient(client).execute(options)
    except ControlError as exc:
        _ = sys.stdout.write(json.dumps(exc.envelope(), ensure_ascii=False) + "\n")
        return 1
    except (ValidationError, ValueError) as exc:
        _ = sys.stdout.write(
            json.dumps({"error": "invalid_arguments", "message": str(exc), "details": None}) + "\n"
        )
        return 2
    else:
        _ = sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
