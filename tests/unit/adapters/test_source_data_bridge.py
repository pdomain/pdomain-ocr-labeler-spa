from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pdomain_ocr_labeler_spa.adapters.source_data import SourceDataBridge, SourceDataError


async def test_missing_configuration_is_explicit() -> None:
    bridge = SourceDataBridge(python=None, corpus_root=None, output_root=None)
    with pytest.raises(SourceDataError, match="configured"):
        _ = await bridge.call({"command": "projects"})


async def test_real_json_module_transport_and_output_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "pdomain_source_data"
    package.mkdir()
    _ = (package / "__init__.py").write_text("")
    _ = (package / "pgdp_review_cli.py").write_text(
        """import json,sys
r=json.load(sys.stdin)
print(json.dumps({"ok":True,"result":{"command":r["command"],"root":r["corpus_root"]}}))
"""
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    bridge = SourceDataBridge(python=Path(sys.executable), corpus_root=tmp_path, output_root=tmp_path)
    result = await bridge.call({"command": "projects"})
    assert result["command"] == "projects"
    assert result["root"] == str(tmp_path)
    tiny = SourceDataBridge(
        python=Path(sys.executable), corpus_root=tmp_path, output_root=tmp_path, max_output_bytes=8
    )
    with pytest.raises(SourceDataError, match="output"):
        _ = await tiny.call({"command": "projects"})


async def test_timeout_cancel_and_malformed_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "pdomain_source_data"
    package.mkdir()
    _ = (package / "__init__.py").write_text("")
    module = package / "pgdp_review_cli.py"
    _ = module.write_text("import time\ntime.sleep(10)\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    bridge = SourceDataBridge(
        python=Path(sys.executable), corpus_root=tmp_path, output_root=tmp_path, timeout_s=0.1
    )
    with pytest.raises(SourceDataError, match="timed out"):
        _ = await bridge.call({"command": "projects"})
    with pytest.raises(SourceDataError, match="cancelled"):
        _ = await bridge.call({"command": "prepare"}, cancelled=lambda: True)
    _ = module.write_text('print("not json")\n')
    # A separate bridge: the 0.1 s budget above is for the hang case and can
    # expire during interpreter startup on a loaded machine.
    patient = SourceDataBridge(
        python=Path(sys.executable), corpus_root=tmp_path, output_root=tmp_path, timeout_s=30
    )
    with pytest.raises(SourceDataError, match="JSON"):
        _ = await patient.call({"command": "projects"})


async def test_output_root_is_resolved_per_operation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "pdomain_source_data"
    package.mkdir()
    (package / ".nobackup").touch()
    _ = (package / "__init__.py").write_text("")
    _ = (package / "pgdp_review_cli.py").write_text("""import json,sys
r=json.load(sys.stdin)
print(json.dumps({'ok':True,'result':{'output_root':r['output_root']}}))
""")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    roots = [tmp_path / "first"]
    bridge = SourceDataBridge(python=Path(sys.executable), corpus_root=tmp_path, output_root=lambda: roots[0])
    assert (await bridge.call({"command": "prepare"}))["output_root"] == str(roots[0])
    roots[0] = tmp_path / "second"
    assert (await bridge.call({"command": "prepare"}))["output_root"] == str(roots[0])
