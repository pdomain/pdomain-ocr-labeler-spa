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
        f"`make help` failed (rc={result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
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
        f"`make -n test` failed (rc={result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # Recipe should mention pytest somewhere.
    assert "pytest" in result.stdout, f"`make -n test` did not render a pytest invocation:\n{result.stdout}"


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
            phony_block.append(line[len(".PHONY:"):])
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
    }
    missing = must_be_phony - declared
    assert not missing, f"targets missing from .PHONY: {sorted(missing)}"
