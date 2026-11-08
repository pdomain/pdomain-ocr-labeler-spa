"""Bounded JSON subprocess boundary to the optional source-data installation."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, final

from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path


@final
class SourceDataError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "source_data_unavailable",
        status: int = 503,
        details: JsonValue = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details


class SourceError(BaseModel):
    code: str
    message: str
    details: JsonValue = None


class SourceEnvelope(BaseModel):
    ok: bool
    result: dict[str, JsonValue] | None = None
    error: SourceError | None = None


@final
class SourceDataBridge:
    def __init__(
        self,
        *,
        python: Path | None,
        corpus_root: Path | None,
        output_root: Path | Callable[[], Path | None] | None,
        timeout_s: float = 120,
        max_output_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        if timeout_s <= 0 or max_output_bytes <= 0:
            raise ValueError("subprocess bounds must be positive")
        self.python = python
        self.corpus_root = corpus_root
        self.output_root = output_root
        self.timeout_s = timeout_s
        self.max_output_bytes = max_output_bytes

    def require_configured(self, *, prepare: bool = False) -> None:
        output_root = self.output_root() if callable(self.output_root) else self.output_root
        if self.python is None or self.corpus_root is None or (prepare and output_root is None):
            raise SourceDataError("source-data Python, corpus and preparation output must be configured")
        if not self.python.is_file():
            raise SourceDataError("configured source-data Python executable is missing")
        if not self.corpus_root.is_dir():
            raise SourceDataError("configured corpus root is missing")

    async def _read(self, stream: asyncio.StreamReader) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while chunk := await stream.read(65536):
            size += len(chunk)
            if size > self.max_output_bytes:
                raise SourceDataError(
                    "source-data output exceeded configured bound", code="source_output_limit", status=502
                )
            chunks.append(chunk)
        return b"".join(chunks)

    async def call(
        self, request: Mapping[str, object], *, cancelled: Callable[[], bool] | None = None
    ) -> dict[str, JsonValue]:
        prepare = request.get("command") == "prepare"
        self.require_configured(prepare=prepare)
        if self.python is None or self.corpus_root is None:
            raise SourceDataError("source-data bridge is not configured")
        body = TypeAdapter[dict[str, JsonValue]](dict[str, JsonValue]).validate_python(request)
        body["corpus_root"] = str(self.corpus_root)
        if prepare:
            output_root = self.output_root() if callable(self.output_root) else self.output_root
            if output_root is None:
                raise SourceDataError("preparation output must be configured")
            body["output_root"] = str(output_root)
        else:
            _ = body.pop("output_root", None)
        try:
            process = await asyncio.create_subprocess_exec(
                str(self.python),
                "-m",
                "pdomain_source_data.pgdp_review_cli",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise SourceDataError(f"cannot start source-data bridge: {exc}") from exc
        if process.stdin is None or process.stdout is None or process.stderr is None:
            process.kill()
            _ = await process.wait()
            raise SourceDataError("source-data subprocess pipes unavailable")

        async def communicate() -> tuple[bytes, bytes]:
            if process.stdin is None or process.stdout is None or process.stderr is None:
                raise SourceDataError("source-data subprocess pipes unavailable")
            process.stdin.write(json.dumps(body).encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
            stdout, stderr = await asyncio.gather(self._read(process.stdout), self._read(process.stderr))
            _ = await process.wait()
            return stdout, stderr

        task = asyncio.create_task(communicate())
        try:
            deadline = asyncio.get_running_loop().time() + self.timeout_s
            while not task.done():
                if cancelled is not None and cancelled():
                    raise SourceDataError("source preparation cancelled", code="source_cancelled", status=409)
                if asyncio.get_running_loop().time() >= deadline:
                    raise SourceDataError("source-data bridge timed out", code="source_timeout", status=504)
                _ = await asyncio.wait({task}, timeout=min(0.05, self.timeout_s))
            stdout, stderr = await task
        except BaseException:
            if process.returncode is None:
                process.kill()
            _ = await process.wait()
            _ = task.cancel()
            _ = await asyncio.gather(task, return_exceptions=True)
            raise
        try:
            envelope = SourceEnvelope.model_validate_json(stdout)
        except ValidationError as exc:
            raise SourceDataError(
                "source-data returned invalid JSON envelope",
                code="source_protocol_error",
                status=502,
                details={
                    "exit_code": process.returncode,
                    "stderr": stderr.decode("utf-8", errors="replace")[-2000:],
                },
            ) from exc
        if not envelope.ok:
            error = envelope.error
            if error is None:
                raise SourceDataError(
                    "source-data error has no details", code="source_protocol_error", status=502
                )
            status = 404 if error.code == "missing_project" else 422
            if error.code == "internal_error":
                status = 502
            raise SourceDataError(error.message, code=error.code, status=status, details=error.details)
        if process.returncode != 0 or envelope.result is None:
            raise SourceDataError(
                "source-data success envelope has invalid exit/result",
                code="source_protocol_error",
                status=502,
            )
        return envelope.result
