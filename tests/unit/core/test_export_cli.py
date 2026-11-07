"""Tests for the headless export CLI (#228).

Spec: docs/specs/2026-05-12-export-design.md §Headless CLI

Acceptance:
- CLI argument parser exists and parses flags correctly.
- --detection-only / --recognition-only / --classification are mutually exclusive.
- No FastAPI import at module level.
- Console script registered in pyproject.toml.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestExportCliNoFastAPI:
    """Verify no FastAPI import happens at module-level."""

    def test_module_importable_without_fastapi(self) -> None:
        """Module must be importable without FastAPI in sys.path."""
        import pdomain_ocr_labeler_spa.core.jobs.handlers.export_cli as cli_mod

        # Check that there are no 'import fastapi' or 'from fastapi' lines
        # outside of function/class bodies (i.e. at module level).
        source_path = Path(cli_mod.__file__)
        source_text = source_path.read_text()
        # Only flag actual import statements, not comments or docstrings.
        import_lines = [
            line.strip()
            for line in source_text.splitlines()
            if line.strip().startswith(("import fastapi", "from fastapi"))
        ]
        assert import_lines == [], f"export_cli.py has module-level FastAPI imports: {import_lines}"


class TestExportCliParser:
    """Argument parser tests."""

    def setup_method(self) -> None:
        from pdomain_ocr_labeler_spa.core.jobs.handlers.export_cli import _build_parser

        self._build_parser = _build_parser

    def test_required_args(self) -> None:
        parser = self._build_parser()
        args = parser.parse_args(["--data-root", "/data", "--project-id", "proj1"])
        assert args.data_root == Path("/data")
        assert args.project_id == "proj1"

    def test_style_filters(self) -> None:
        parser = self._build_parser()
        args = parser.parse_args(
            [
                "--data-root",
                "/data",
                "--project-id",
                "proj1",
                "--style",
                "italic",
                "bold",
            ]
        )
        assert args.style_filters == ["italic", "bold"]

    def test_detection_only_flag(self) -> None:
        parser = self._build_parser()
        args = parser.parse_args(
            [
                "--data-root",
                "/data",
                "--project-id",
                "proj1",
                "--detection-only",
            ]
        )
        assert args.detection_only is True
        assert args.recognition_only is False

    def test_recognition_only_flag(self) -> None:
        parser = self._build_parser()
        args = parser.parse_args(
            [
                "--data-root",
                "/data",
                "--project-id",
                "proj1",
                "--recognition-only",
            ]
        )
        assert args.recognition_only is True
        assert args.detection_only is False

    def test_classification_flag(self) -> None:
        parser = self._build_parser()
        args = parser.parse_args(
            [
                "--data-root",
                "/data",
                "--project-id",
                "proj1",
                "--classification",
            ]
        )
        assert args.classification is True

    def test_mutually_exclusive_output_flags(self) -> None:
        """--detection-only and --recognition-only cannot both be set."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from pdomain_ocr_labeler_spa.core.jobs.handlers.export_cli import _build_parser;"
                    "_build_parser().parse_args(['--data-root','/d','--project-id','p',"
                    "'--detection-only','--recognition-only'])"
                ),
            ],
            capture_output=True,
            text=True,
        )
        # argparse.error exits with code 2
        assert result.returncode == 2

    def test_page_index_flag(self) -> None:
        parser = self._build_parser()
        args = parser.parse_args(
            [
                "--data-root",
                "/data",
                "--project-id",
                "proj1",
                "--page-index",
                "3",
            ]
        )
        assert args.page_index == 3

    def test_component_filter(self) -> None:
        parser = self._build_parser()
        args = parser.parse_args(
            [
                "--data-root",
                "/data",
                "--project-id",
                "proj1",
                "--component",
                "footnote",
            ]
        )
        assert args.component_filter == "footnote"


class TestRunExport:
    """Unit tests for the _run_export coroutine."""

    @pytest.mark.asyncio
    async def test_no_pages_returns_zero(self, tmp_path: Path) -> None:
        from pdomain_ocr_labeler_spa.core.jobs.handlers.export_cli import _run_export

        count = await _run_export(
            data_root=tmp_path,
            project_id="nonexistent",
            style_filters=[],
            component_filter=None,
            detection_only=False,
            recognition_only=False,
            classification=False,
            page_index=None,
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_single_page_export_calls_export_page(self, tmp_path: Path) -> None:
        """_run_export delegates to _export_page for each page."""
        from pdomain_ocr_labeler_spa.core.jobs.handlers.export_cli import _run_export

        # Set up a minimal labeled project dir with one page
        labeled_dir = tmp_path / "labeled-projects" / "proj1"
        labeled_dir.mkdir(parents=True)
        page_file = labeled_dir / "proj1_000.json"
        # Minimal envelope content
        page_file.write_text('{"version": "2.1.0", "payload": {"pages": []}}')

        # Fake image alongside the page
        image_path = labeled_dir / "proj1_000.png"
        image_path.write_bytes(b"\x89PNG\r\n")

        mock_page = MagicMock()
        mock_page.words = []

        # Patch in the source module (export.py) since _run_export imports from there
        with (
            patch(
                "pdomain_ocr_labeler_spa.core.jobs.handlers.export._load_page_from_envelope_file",
                return_value=mock_page,
            ),
            patch(
                "pdomain_ocr_labeler_spa.core.jobs.handlers.export._page_is_validated",
                return_value=True,
            ),
            patch(
                "pdomain_ocr_labeler_spa.core.jobs.handlers.export._resolve_image_path",
                return_value=image_path,
            ),
            patch(
                "pdomain_ocr_labeler_spa.core.jobs.handlers.export._scan_labeled_pages",
                return_value=[page_file],
            ),
            patch(
                "pdomain_ocr_labeler_spa.core.jobs.handlers.export._export_page",
            ) as mock_export,
        ):
            count = await _run_export(
                data_root=tmp_path,
                project_id="proj1",
                style_filters=[],
                component_filter=None,
                detection_only=False,
                recognition_only=False,
                classification=False,
                page_index=None,
            )

        assert count == 1
        mock_export.assert_called_once()

    @pytest.mark.asyncio
    async def test_style_folders_use_one_snapshot_export(self, tmp_path: Path) -> None:
        """Every style folder goes through one snapshot export, not a raw loop."""
        from pdomain_ocr_labeler_spa.core.jobs.handlers.export_cli import _run_export

        labeled_dir = tmp_path / "labeled-projects" / "proj1"
        labeled_dir.mkdir(parents=True)
        page_file = labeled_dir / "proj1_000.json"
        page_file.write_text('{"version": "2.1.0", "payload": {"pages": []}}')
        image_path = labeled_dir / "proj1_000.png"
        image_path.write_bytes(b"\x89PNG\r\n")

        mock_page = MagicMock()
        mock_page.words = []

        with (
            patch(
                "pdomain_ocr_labeler_spa.core.jobs.handlers.export._load_page_from_envelope_file",
                return_value=mock_page,
            ),
            patch(
                "pdomain_ocr_labeler_spa.core.jobs.handlers.export._page_is_validated",
                return_value=True,
            ),
            patch(
                "pdomain_ocr_labeler_spa.core.jobs.handlers.export._resolve_image_path",
                return_value=image_path,
            ),
            patch(
                "pdomain_ocr_labeler_spa.core.jobs.handlers.export._scan_labeled_pages",
                return_value=[page_file],
            ),
            patch(
                "pdomain_ocr_labeler_spa.core.jobs.handlers.export._export_page_to_output_roots",
            ) as mock_export,
        ):
            count = await _run_export(
                data_root=tmp_path,
                project_id="proj1",
                style_filters=["italics", "bold"],
                component_filter=None,
                detection_only=False,
                recognition_only=False,
                classification=False,
                page_index=None,
            )

        assert count == 1
        mock_export.assert_called_once()
        output_roots = mock_export.call_args.args[2]
        assert set(output_roots) == {"italics", "bold"}


class TestConsoleScriptRegistration:
    """Verify the console script is registered in pyproject.toml."""

    def test_console_script_in_pyproject(self) -> None:
        root = Path(__file__).parents[3]
        pyproject = root / "pyproject.toml"
        assert pyproject.exists(), "pyproject.toml not found"
        text = pyproject.read_text()
        assert "pdomain-ocr-labeler-spa-export" in text, (
            "Console script 'pdomain-ocr-labeler-spa-export' not registered in pyproject.toml"
        )
        assert "export_cli:main" in text, "Console script entry-point 'export_cli:main' not in pyproject.toml"
