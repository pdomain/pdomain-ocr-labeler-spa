"""Unit tests for the P0-CI-SOFT skip-budget gate in ``conftest.py``.

Pure logic — no ``live_server``/browser fixtures needed. Runs under both
``make e2e`` (harmlessly; nothing here skips) and ``make exercise-real``.

Spec: docs/issues/2026-07-21-e2e-non-blocking-soft-skips.md
"""

from __future__ import annotations

from tests.e2e.conftest import _ALLOWED_SKIP_PREFIXES, _skip_budget_exempt_file


def test_exercise_real_project_file_is_exempt() -> None:
    """``make exercise-real`` (pytest tests/e2e/exercise_real_project.py) must
    not be caught by the skip-budget gate meant for ``make e2e``.

    That module's ~90 CU-2.2 placeholder stubs
    (``@pytest.mark.skip("TODO: walk in browser — CU-2.2")``) are pre-existing,
    already-tracked debt, not a new soft-skip `make e2e` should fail on.
    """
    nodeid = "tests/e2e/exercise_real_project.py::test_phase_1_1_something[chromium]"
    assert _skip_budget_exempt_file(nodeid)


def test_other_e2e_files_are_not_exempt() -> None:
    """The exemption is scoped to exercise_real_project.py only."""
    nodeid = "tests/e2e/test_ui_coverage.py::test_worklist_sort_select_changes[chromium]"
    assert not _skip_budget_exempt_file(nodeid)


def test_exercise_fixture_missing_is_an_allowed_skip_reason() -> None:
    """``exercise_server`` skips with this reason when the committed fixture
    data is absent — the same kind of environment precondition as the
    allowlisted "SPA not built" skip beside it, so it must give its own
    actionable message instead of failing the session for an unrelated
    reason.
    """
    reason = "Exercise fixture missing — run: uv run python scripts/generate_exercise_fixture.py"
    assert reason.startswith(_ALLOWED_SKIP_PREFIXES)
