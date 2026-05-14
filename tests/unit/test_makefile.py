"""Smoke tests for the repo Makefile.

These guard against accidental syntax errors that would hide behind the
fact that most contributors only invoke a couple of targets manually
(`make test`, `make frontend-build`). The unit-test suite exercises the
parse + dry-run path so a malformed recipe surfaces in CI rather than
the first time someone needs `make build`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"


def _have_make() -> bool:
    return shutil.which("make") is not None


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_makefile_exists() -> None:
    assert MAKEFILE.exists(), f"Makefile missing at {MAKEFILE}"


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_makefile_help_target_runs() -> None:
    """`make help` should parse the Makefile and exit 0.

    `help` is recipe-only (no shell side effects beyond grep/awk), so it
    is the cheapest way to assert the file parses cleanly.
    """
    result = subprocess.run(
        ["make", "-C", str(REPO_ROOT), "help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        f"`make help` failed (rc={result.returncode}):\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # Sanity: a few key targets should appear in help output.
    for target in ("test", "frontend-install", "frontend-build", "build", "ci"):
        assert target in result.stdout, f"target '{target}' missing from `make help` output"


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_makefile_dry_run_test_target() -> None:
    """`make -n test` should dry-run-render the test recipe without errors.

    `-n` (no-exec) tells make to print the recipe lines without running
    them, which exercises the parser + variable expansion. A typo in any
    target the recipe depends on would surface here.
    """
    result = subprocess.run(
        ["make", "-C", str(REPO_ROOT), "-n", "test"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        f"`make -n test` failed (rc={result.returncode}):\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # Recipe should mention pytest somewhere.
    assert "pytest" in result.stdout, f"`make -n test` did not render a pytest invocation:\n{result.stdout}"


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_makefile_run_target_dry_runs_and_invokes_ui() -> None:
    """`make -n run` should reference frontend-build and the UI entry point.

    `make run` is the user-facing "just run the labeler" target —
    distinct from `make dev` (which expects Vite on :5173). It must:
    - Ensure the SPA bundle exists (depend on / call `frontend-build`).
    - Launch `pd-ocr-labeler-ui` without `--reload` and without
      `--frontend-dev` (we are SERVING the bundle, not developing it).

    Asserting on the dry-run output keeps the test fast and lets us
    catch accidental regressions like dropping the dependency or
    flipping `--reload` back on.
    """
    result = subprocess.run(
        ["make", "-C", str(REPO_ROOT), "-n", "run"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        f"`make -n run` failed (rc={result.returncode}):\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    out = result.stdout
    # Either the recipe shells out to frontend-build, or it depends on
    # it (in which case `make -n` renders the dependency's recipe
    # first). Either way the dry-run output must mention the SPA build.
    assert "frontend-build" in out or "Building frontend" in out, (
        f"`make -n run` should ensure the SPA is built before serving:\n{out}"
    )
    assert "pd-ocr-labeler-ui" in out, f"`make -n run` should launch pd-ocr-labeler-ui:\n{out}"
    # Must NOT enable reload or frontend-dev — those are `make dev`'s job.
    assert "--reload" not in out, f"`make run` must not enable --reload:\n{out}"
    assert "--frontend-dev" not in out, f"`make run` must not enable --frontend-dev:\n{out}"


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_makefile_help_lists_run_target() -> None:
    """`make help` should advertise the `run` target alongside `dev`."""
    result = subprocess.run(
        ["make", "-C", str(REPO_ROOT), "help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert "run " in result.stdout or "run\t" in result.stdout or "\nrun" in result.stdout, (
        f"`run` target missing from help output:\n{result.stdout}"
    )


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_makefile_phony_targets_declared() -> None:
    """All recipe-only targets we care about should be declared .PHONY.

    Forgetting `.PHONY` is a subtle bug — a stray file/dir named the
    same as a target silently disables the recipe. We don't enumerate
    every target; we spot-check the ones most likely to clash with
    accidental directories.
    """
    text = MAKEFILE.read_text()
    # The first .PHONY line in the file (continuation lines start with whitespace).
    phony_block = []
    in_block = False
    for line in text.splitlines():
        if line.startswith(".PHONY:"):
            in_block = True
            phony_block.append(line[len(".PHONY:") :])
            continue
        if in_block:
            if line.endswith("\\") or line.startswith((" ", "\t")):
                phony_block.append(line)
                if not line.rstrip().endswith("\\"):
                    break
            else:
                break

    declared = set()
    for chunk in phony_block:
        for tok in chunk.replace("\\", " ").split():
            declared.add(tok)

    must_be_phony = {
        "help",
        "setup",
        "test",
        "build",
        "clean",
        "ci",
        "frontend-install",
        "frontend-build",
        "frontend-test",
        "frontend-dev",
        "openapi-export",
        "lint",
        "format",
        "run",
    }
    missing = must_be_phony - declared
    assert not missing, f"targets missing from .PHONY: {sorted(missing)}"


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_ci_calls_pre_commit_check() -> None:
    """`make ci` must invoke pre-commit-check so hooks run in CI."""
    result = subprocess.run(
        ["make", "-C", str(REPO_ROOT), "-n", "ci"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"`make -n ci` failed (rc={result.returncode}):\n{result.stderr}"
    assert "pre-commit run" in result.stdout, (
        f"`make ci` does not call pre-commit-check (pre-commit run --all-files):\n{result.stdout}"
    )


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_ci_calls_openapi_export_before_frontend_build() -> None:
    """`make ci` must call openapi-export before frontend-build."""
    result = subprocess.run(
        ["make", "-C", str(REPO_ROOT), "-n", "ci"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"`make -n ci` failed (rc={result.returncode}):\n{result.stderr}"
    out = result.stdout
    assert "openapi" in out.lower(), f"`make ci` does not call openapi-export:\n{out}"
    assert "frontend" in out.lower(), f"`make ci` does not call frontend-build:\n{out}"
    openapi_pos = out.lower().find("openapi")
    frontend_build_pos = out.lower().find("building frontend")
    if frontend_build_pos == -1:
        frontend_build_pos = out.lower().find("frontend-build")
    assert openapi_pos < frontend_build_pos, (
        f"openapi-export must appear before frontend-build in `make ci` output:\n{out}"
    )


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_ci_runs_frontend_install_before_pre_commit_check() -> None:
    """`make ci` must run frontend-install before pre-commit-check.

    Issue #279: the frontend pre-commit hooks (frontend-tsc, frontend-eslint,
    frontend-prettier) invoke `npm run` / `npx`, which fail with
    `tsc/eslint/prettier not found` if node_modules does not exist.
    Running frontend-install first ensures node_modules is populated
    before pre-commit-check fires the hooks.
    """
    # Read the Makefile directly to check the ci target's dependency order.
    # `make -n ci` expands all dependencies recursively, but the ordering
    # we care about is at the ci target level, which is most clearly
    # verified by reading the target line.
    makefile_text = MAKEFILE.read_text()
    # Find the ci target line
    ci_line = ""
    for line in makefile_text.splitlines():
        if line.startswith("ci:"):
            ci_line = line
            break
    assert ci_line, "ci: target not found in Makefile"
    # Both dependencies must appear on the ci target line
    assert "frontend-install" in ci_line, (
        f"frontend-install missing from `ci:` target dependencies: {ci_line!r}"
    )
    assert "pre-commit-check" in ci_line, (
        f"pre-commit-check missing from `ci:` target dependencies: {ci_line!r}"
    )
    # frontend-install must appear before pre-commit-check
    fi_pos = ci_line.index("frontend-install")
    pc_pos = ci_line.index("pre-commit-check")
    assert fi_pos < pc_pos, (
        f"frontend-install must appear before pre-commit-check in ci: target "
        f"so node_modules exists when pre-commit hooks fire; got: {ci_line!r}"
    )
