"""Contract tests: the public ``Job``/``JobType``/``JobStatus`` models agree
with what the runner actually produces.

``docs/issues/2026-07-21-jobs-api-openapi-mismatch.md`` (P1-JOBS-API): the
public wire model and the runner's internal record drifted because nothing
proved they agreed. These tests are that proof — each one fails the moment
a handler is registered without a matching ``JobType`` member, a runner
status is added without a matching public ``JobStatus`` member, or
``to_public_job`` stops mapping every runner field.
"""

from __future__ import annotations

import importlib
import inspect
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pydantic
import pytest

from pdomain_ocr_labeler_spa.core.jobs import runner as runner_module
from pdomain_ocr_labeler_spa.core.jobs.runner import Job as RunnerJob
from pdomain_ocr_labeler_spa.core.jobs.runner import (
    JobStatus as RunnerJobStatus,
)
from pdomain_ocr_labeler_spa.core.jobs.runner import (
    payload_result_keys,
    registered_handlers,
    registered_job_types,
    to_public_job,
)
from pdomain_ocr_labeler_spa.core.models import Job as PublicJob
from pdomain_ocr_labeler_spa.core.models import JobProgress as PublicJobProgress
from pdomain_ocr_labeler_spa.core.models import JobStatus as PublicJobStatus
from pdomain_ocr_labeler_spa.core.models import JobType as PublicJobType


def test_every_registered_handler_has_a_job_type_member() -> None:
    """Every ``job_type`` string a handler is registered under must be a
    ``JobType`` enum member — and vice versa, so the enum never lists a type
    the runner cannot actually run."""
    handler_types = registered_job_types()
    enum_values = {member.value for member in PublicJobType}
    assert handler_types == enum_values, (
        f"JobType enum vs. registered handlers disagree: "
        f"handlers only={handler_types - enum_values}, enum only={enum_values - handler_types}"
    )


def test_every_runner_status_has_a_public_status_member() -> None:
    """The public ``JobStatus`` must reach every status the runner can set."""
    runner_values = {member.value for member in RunnerJobStatus}
    public_values = {member.value for member in PublicJobStatus}
    assert runner_values == public_values, (
        f"JobStatus enums disagree: runner only={runner_values - public_values}, "
        f"public only={public_values - runner_values}"
    )


def _make_runner_job(
    *,
    job_id: str = "job-1",
    job_type: str = "export",
    status: RunnerJobStatus = RunnerJobStatus.RUNNING,
    project_id: str | None = "proj-1",
    progress_current: int = 3,
    progress_total: int = 10,
    message: str = "working",
    error_message: str = "",
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> RunnerJob:
    return RunnerJob(
        job_id=job_id,
        job_type=job_type,
        status=status,
        project_id=project_id,
        progress_current=progress_current,
        progress_total=progress_total,
        message=message,
        error_message=error_message,
        payload=payload or {},
        result=result or {},
        created_at=created_at or datetime.now(UTC),
        started_at=started_at,
        completed_at=completed_at,
    )


def test_to_public_job_maps_every_field() -> None:
    """``to_public_job`` renames runner fields onto the declared ``Job`` model."""
    runner_job = _make_runner_job()
    public_job = to_public_job(runner_job)

    assert isinstance(public_job, PublicJob)
    assert public_job.id == runner_job.job_id
    assert public_job.type.value == runner_job.job_type
    assert public_job.project_id == runner_job.project_id
    assert public_job.status.value == runner_job.status.value
    assert public_job.progress.current == runner_job.progress_current
    assert public_job.progress.total == runner_job.progress_total
    assert public_job.progress.message == runner_job.message
    assert public_job.created_at == runner_job.created_at


def test_to_public_job_maps_empty_error_message_to_none() -> None:
    """Runner ``error_message`` defaults to ``""``; the public model uses
    ``None`` for "no error" instead."""
    runner_job = _make_runner_job(error_message="")
    assert to_public_job(runner_job).error_message is None


def test_to_public_job_carries_a_real_error_message() -> None:
    runner_job = _make_runner_job(error_message="boom")
    assert to_public_job(runner_job).error_message == "boom"


def test_to_public_job_updated_at_prefers_completed_then_started_then_created() -> None:
    created = datetime(2026, 1, 1, tzinfo=UTC)
    started = datetime(2026, 1, 2, tzinfo=UTC)
    completed = datetime(2026, 1, 3, tzinfo=UTC)

    only_created = _make_runner_job(created_at=created)
    assert to_public_job(only_created).updated_at == created

    with_started = _make_runner_job(created_at=created, started_at=started)
    assert to_public_job(with_started).updated_at == started

    with_completed = _make_runner_job(created_at=created, started_at=started, completed_at=completed)
    assert to_public_job(with_completed).updated_at == completed


def test_to_public_job_rejects_an_unregistered_job_type() -> None:
    """An internal job whose ``job_type`` has no ``JobType`` member must
    raise loudly, never silently coerce to a wrong public type."""
    runner_job = _make_runner_job(job_type="not_a_real_job_type")
    with pytest.raises(ValueError, match="not_a_real_job_type"):
        to_public_job(runner_job)


# ── result field: handler-written payload/result data reaches the public model ──


@pytest.mark.parametrize("status", [RunnerJobStatus.COMPLETE, RunnerJobStatus.CANCELLED])
def test_to_public_job_carries_save_project_skipped_page_result(status: RunnerJobStatus) -> None:
    """A cancelled or completed ``save_project`` job's ``payload["skipped_pages"]``/
    ``payload["skipped_indices"]`` (written by ``handle_save_project``) must be
    reachable through the public model — ``PageActionsCompact`` reads exactly
    this to warn a person that pages were skipped
    (docs/issues/2026-07-21-jobs-api-openapi-mismatch.md, P1-JOBS-API)."""
    runner_job = _make_runner_job(
        job_type="save_project",
        status=status,
        payload={
            "failures": [{"page_index": 2, "error": "disk full"}],
            "skipped_pages": 1,
            "skipped_indices": [3],
        },
        completed_at=datetime.now(UTC),
    )

    public_job = to_public_job(runner_job)

    assert public_job.result is not None
    assert public_job.result.get("skipped_pages") == 1
    assert public_job.result.get("skipped_indices") == [3]
    assert public_job.result.get("failures") == [{"page_index": 2, "error": "disk full"}]


def test_to_public_job_result_is_none_when_nothing_was_written() -> None:
    runner_job = _make_runner_job(payload={}, result={})
    assert to_public_job(runner_job).result is None


def test_job_result_rejects_wrong_value_type_for_a_known_key() -> None:
    """``Job.result`` is a typed ``JobResult`` (a ``TypedDict``), not
    ``dict[str, Any]`` — pydantic validates known keys' value types.
    Under the old ``dict[str, Any] | None`` field type, an ``Any`` value
    was accepted for every key, so this would not have raised."""
    with pytest.raises(pydantic.ValidationError):
        PublicJob(
            id="job-1",
            type=PublicJobType.SAVE_PROJECT,
            project_id="proj-1",
            status=PublicJobStatus.COMPLETE,
            progress=PublicJobProgress(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            result={"skipped_pages": "not-an-int"},  # pyright: ignore[reportArgumentType]
        )


def test_to_public_job_merges_job_result_alongside_payload_output_keys() -> None:
    """The export terminal-stats channel (``job.result``, merged flat into the
    SSE frame today) and the ``job.payload`` output channel (``save_project``/
    ``refine_bboxes``/``propose_page_kinds``) both land in the same public
    ``result`` field — the two paths agree at the public-model boundary."""
    runner_job = _make_runner_job(
        job_type="export",
        payload={"skipped_pages": 0},
        result={"words_exported_detection": 5},
    )
    public_job = to_public_job(runner_job)
    assert public_job.result == {"skipped_pages": 0, "words_exported_detection": 5}


# ── static-scan machinery for the payload-write contract test below ───────────

_LAZY_IMPORT_RE = re.compile(r"from\s+(\.[\w.]*)\s+import\s+\w+")
_LITERAL_KEY_RE = re.compile(r"""^(['"])([A-Za-z0-9_]+)\1$""")
_PAYLOAD_SUBSCRIPT_WRITE_RE = re.compile(r"job\.payload\[([^\]]*)\]\s*=")
_PAYLOAD_UPDATE_CALL_RE = re.compile(r"job\.payload\.update\(")


def _resolve_handler_target_modules() -> dict[str, Path]:
    """Statically resolve, from the ``_HANDLERS`` registry, which module
    file each registered handler's real implementation lives in.

    Each wrapper in ``registered_handlers()`` does a lazy ``from
    .handlers.<name> import <fn>`` inside its body (to dodge import
    cycles / heavy deps at import time). This reads that import line out
    of the wrapper's own source via ``inspect.getsource`` and resolves it
    relative to the wrapper's package — not a glob over
    ``core/jobs/handlers/`` — so a handler registered from a module
    outside that directory is still found.
    """
    modules: dict[str, Path] = {}
    for job_type, wrapper in registered_handlers().items():
        source = inspect.getsource(wrapper)
        match = _LAZY_IMPORT_RE.search(source)
        assert match is not None, (
            f"handler wrapper for {job_type!r} ({wrapper.__name__}) has no "
            "`from .<module> import <fn>` lazy import in its source — "
            "update _resolve_handler_target_modules to find its real module"
        )
        target_module = importlib.import_module(match.group(1), package=runner_module.__package__)
        target_file = inspect.getfile(target_module)
        modules[job_type] = Path(target_file)
    return modules


def _scan_module_source_for_payload_writes(source: str) -> tuple[set[str], list[str]]:
    """Return ``(literal_keys, opaque_sites)`` found in one module's source.

    ``literal_keys``: every key from a ``job.payload["literal"] = ...``
    write (single- or double-quoted). ``opaque_sites``: a human-readable
    description of any write this scan cannot statically resolve to a
    literal key — a computed subscript (``job.payload[some_expr] =
    ...``) or a ``job.payload.update(...)`` call — since the allowlist
    cannot verify a key it cannot see.
    """
    literal_keys: set[str] = set()
    opaque: list[str] = []
    for raw_key in _PAYLOAD_SUBSCRIPT_WRITE_RE.findall(source):
        stripped = raw_key.strip()
        match = _LITERAL_KEY_RE.match(stripped)
        if match:
            literal_keys.add(match.group(2))
        else:
            opaque.append(f"job.payload[{stripped}] = ...")
    if _PAYLOAD_UPDATE_CALL_RE.search(source):
        opaque.append("job.payload.update(...)")
    return literal_keys, opaque


def test_resolve_handler_target_modules_covers_every_registered_handler() -> None:
    """The registry-derived module list must name a real, existing file for
    every registered job type — the same universe ``registered_job_types()``
    proves matches ``JobType``."""
    modules = _resolve_handler_target_modules()
    assert set(modules) == registered_job_types()
    for job_type, path in modules.items():
        assert path.is_file(), f"{job_type}: resolved module {path} does not exist"
        assert path.suffix == ".py"


def test_scan_module_source_finds_literal_payload_keys() -> None:
    source = "job.payload[\"skipped_pages\"] = 1\njob.payload['run_id'] = value\n"
    literal_keys, opaque = _scan_module_source_for_payload_writes(source)
    assert literal_keys == {"skipped_pages", "run_id"}
    assert opaque == []


def test_scan_module_source_flags_non_literal_key_writes() -> None:
    """A computed key (``job.payload[key_var] = ...``) escapes the literal
    regex the allowlist check relies on — this must be flagged, not
    silently ignored, since it is exactly how a real handler output key
    could go undetected."""
    source = "job.payload[key_var] = 1\n"
    literal_keys, opaque = _scan_module_source_for_payload_writes(source)
    assert literal_keys == set()
    assert len(opaque) == 1
    assert "key_var" in opaque[0]


def test_scan_module_source_flags_update_calls() -> None:
    """``job.payload.update(...)`` can write arbitrary keys through one call
    site — always flagged as opaque rather than attempting to parse its
    argument."""
    source = "job.payload.update(extra_fields)\n"
    literal_keys, opaque = _scan_module_source_for_payload_writes(source)
    assert literal_keys == set()
    assert opaque == ["job.payload.update(...)"]


def test_payload_result_keys_cover_every_key_a_handler_writes() -> None:
    """Contract test: every literal ``job.payload["<key>"] = ...`` write in
    any registered handler's real module must be in ``payload_result_keys()``
    — the allowlist ``to_public_job`` uses to surface ``job.payload`` output
    through the public model. A handler that starts writing a new output key
    without updating the allowlist fails this test instead of silently
    dropping the field off the wire, the way ``skipped_pages``/
    ``skipped_indices`` did (docs/issues/2026-07-21-jobs-api-openapi-mismatch.md,
    P1-JOBS-API).

    Hardened over the first version of this test (2026-09-17 review): the
    handler module list is derived from the ``_HANDLERS`` registry itself
    (``_resolve_handler_target_modules``), not a glob over
    ``core/jobs/handlers/``, so a handler registered from a module outside
    that directory is still covered; and any payload write this scan cannot
    resolve to a literal string key — a computed subscript or a
    ``job.payload.update(...)`` call — fails the test outright instead of
    silently passing, since the allowlist cannot verify a key it cannot see.

    What this still cannot catch: a key written through a *helper function
    defined in a different module* that the handler calls (e.g. a shared
    ``_record_result(job, **kwargs)`` living outside the handler's own
    resolved file) — that would require tracing the handler's call graph,
    which is exactly the "running every handler" cost this static check
    exists to avoid. A handler that delegates its payload writes that way
    needs a manual audit; this test only proves the handler's *own* module
    is clean.
    """
    literal_keys: set[str] = set()
    opaque_sites: list[str] = []
    for job_type, path in _resolve_handler_target_modules().items():
        found_keys, found_opaque = _scan_module_source_for_payload_writes(path.read_text(encoding="utf-8"))
        literal_keys |= found_keys
        opaque_sites.extend(f"{job_type} ({path.name}): {site}" for site in found_opaque)

    assert not opaque_sites, (
        "handler module(s) write job.payload through a site this test cannot "
        f"statically verify against the allowlist: {opaque_sites} — use a "
        "literal string key, or audit manually and extend this test"
    )

    allowlist = payload_result_keys()
    missing = literal_keys - allowlist
    assert not missing, (
        f"handler(s) write job.payload key(s) not in payload_result_keys(): {missing} "
        f"— add them to runner._PAYLOAD_RESULT_KEYS so to_public_job() surfaces them"
    )
