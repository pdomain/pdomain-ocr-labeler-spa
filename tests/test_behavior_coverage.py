from pathlib import Path

from scripts.behavior_coverage import (
    Record,
    build_report,
    render_markdown,
    scan_cited,
    scan_declared,
    scan_frontend_cited,
)


def test_scan_declared_finds_ids_and_regression_flag(tmp_path: Path) -> None:
    doc = tmp_path / "screen-home.md"
    doc.write_text(
        "# Screen behavior spec - Home\n\n"
        "### B-HOME-001 - Upload a ZIP\n\n"
        "- **Regression:** no\n\n"
        "### B-HOME-002 - Reject bad file\n\n"
        "- **Regression:** yes (#fixed-2026-04)\n",
        encoding="utf-8",
    )
    declared = scan_declared(tmp_path)
    assert declared["B-HOME-001"].regression is False
    assert declared["B-HOME-002"].regression is True


def test_scan_cited_finds_docstring_and_marker(tmp_path: Path) -> None:
    test_file = tmp_path / "test_x.py"
    test_file.write_text(
        'def test_a():\n    """Covers: B-HOME-001"""\n    pass\n\n'
        '@behavior("B-HOME-002")\n'
        "def test_b():\n    pass\n",
        encoding="utf-8",
    )
    cited = scan_cited(tmp_path)
    assert cited == {"B-HOME-001", "B-HOME-002"}


def test_scan_cited_skips_own_test_file(tmp_path: Path) -> None:
    self_test = tmp_path / "test_behavior_coverage.py"
    self_test.write_text(
        'def test_x():\n    """Covers: B-HOME-001"""\n    pass\n',
        encoding="utf-8",
    )
    assert scan_cited(tmp_path) == set()


def test_build_report_flags_orphan_regression_and_unlinked() -> None:
    declared = {
        "B-HOME-001": Record("B-HOME-001", regression=False),
        "B-HOME-002": Record("B-HOME-002", regression=True),
        "B-HOME-003": Record("B-HOME-003", regression=True),
    }
    cited = {"B-HOME-003", "B-RESULTS-999"}
    report = build_report(declared, cited)
    assert report.orphans == {"B-HOME-001", "B-HOME-002"}
    assert report.unlinked == {"B-RESULTS-999"}
    assert report.uncovered_regressions == {"B-HOME-002"}
    assert report.ok is False


def test_build_report_ok_when_clean() -> None:
    declared = {"B-HOME-001": Record("B-HOME-001", regression=True)}
    report = build_report(declared, {"B-HOME-001"})
    assert report.ok is True
    assert report.uncovered_regressions == set()
    assert report.unlinked == set()


def test_render_markdown_lists_status() -> None:
    declared = {
        "B-HOME-001": Record("B-HOME-001", regression=False),
        "B-HOME-003": Record("B-HOME-003", regression=True),
    }
    report = build_report(declared, {"B-HOME-003"})
    md = render_markdown(report)
    assert md.startswith("<!-- docgraph: ignore -->\n\n")
    assert "B-HOME-001" in md
    assert "specified" in md
    assert "test-written" in md
    assert "do not edit" in md.lower()


def test_scan_declared_finds_multi_segment_flow_id(tmp_path: Path) -> None:
    doc = tmp_path / "flows.md"
    doc.write_text(
        "# Cross-unit flows\n\n"
        "### F-LABEL-SAVE-EXPORT-01 - Flagship path\n\n"
        "- **Regression:** no\n\n"
        "### F-RERUN-01 - Single-page rerun\n\n"
        "- **Regression:** yes\n",
        encoding="utf-8",
    )
    declared = scan_declared(tmp_path)
    assert "F-LABEL-SAVE-EXPORT-01" in declared
    assert "F-RERUN-01" in declared
    assert declared["F-LABEL-SAVE-EXPORT-01"].regression is False
    assert declared["F-RERUN-01"].regression is True


def test_scan_cited_finds_multi_segment_flow_id(tmp_path: Path) -> None:
    test_file = tmp_path / "test_flows.py"
    test_file.write_text(
        'def test_flagship():\n    """Covers: F-LABEL-SAVE-EXPORT-01"""\n    pass\n\n'
        'def test_rerun():\n    """Covers: F-RERUN-01"""\n    pass\n',
        encoding="utf-8",
    )
    cited = scan_cited(tmp_path)
    assert "F-LABEL-SAVE-EXPORT-01" in cited
    assert "F-RERUN-01" in cited


def test_scan_frontend_cited_finds_vitest_comments(tmp_path: Path) -> None:
    src = tmp_path / "frontend" / "src"
    src.mkdir(parents=True)
    (src / "Widget.test.tsx").write_text(
        "// Covers: B-WIDGET-001, F-WIDGET-ROUNDTRIP-01\nit('works', () => {})\n",
        encoding="utf-8",
    )
    (src / "Widget.tsx").write_text(
        "// Covers: B-WIDGET-999\n",
        encoding="utf-8",
    )

    cited = scan_frontend_cited(src)

    assert cited == {"B-WIDGET-001", "F-WIDGET-ROUNDTRIP-01"}
