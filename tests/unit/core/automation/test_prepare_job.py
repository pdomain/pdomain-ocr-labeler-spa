from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from pdomain_ocr_labeler_spa.adapters.source_data import SourceDataBridge
from pdomain_ocr_labeler_spa.core.jobs.events import JobEventBroker
from pdomain_ocr_labeler_spa.core.jobs.runner import JobRunner, JobStatus, to_public_job


async def test_terminal_prep_job_preserves_source_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "pdomain_source_data"
    package.mkdir()
    (package / ".nobackup").touch()
    _ = (package / "__init__.py").write_text("")
    _ = (package / "pgdp_review_cli.py").write_text("""import json,sys
json.load(sys.stdin)
error={'code':'missing_rounds','message':'P3 missing','details':{'round':'P3'}}
print(json.dumps({'ok':False,'error':error}))
sys.exit(2)
""")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    bridge = SourceDataBridge(python=Path(sys.executable), corpus_root=tmp_path, output_root=tmp_path)
    runner = JobRunner(JobEventBroker(), context={"source_data": bridge})
    job_id = runner.submit_idempotent(
        "prepare_pgdp", request_id="prep", payload={"project_id": "p", "page_keys": ["01.png"]}
    )
    background = asyncio.create_task(runner.run_forever())
    try:
        async with asyncio.timeout(3):
            while True:
                job = runner.get_job(job_id)
                assert job is not None
                if job.status == JobStatus.ERROR:
                    break
                await asyncio.sleep(0.01)
        result = to_public_job(job).result
        assert result is not None
        assert "source_error" in result
        assert result["source_error"] == {
            "error": "missing_rounds",
            "message": "P3 missing",
            "details": {"round": "P3"},
        }
        assert (
            runner.lookup_idempotent(
                "prepare_pgdp", request_id="prep", payload={"project_id": "p", "page_keys": ["01.png"]}
            )
            == job_id
        )
    finally:
        await runner.stop()
        await background
