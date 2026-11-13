"""Smoke tests for the repo justfile.

These guard against accidental syntax errors that would hide behind the
fact that most contributors only invoke a couple of targets manually
(`just test`, `just frontend-build`). The unit-test suite exercises the
parse + dry-run path so a malformed recipe surfaces in CI rather than
the first time someone needs `just build`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = REPO_ROOT / "justfile"


def _have_just() -> bool:
    return shutil.which("just") is not None


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_justfile_exists() -> None:
    assert JUSTFILE.exists(), f"justfile missing at {JUSTFILE}"


def test_make_shim_is_removed() -> None:
    assert not (REPO_ROOT / "Makefile").exists()


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_makefile_help_target_runs() -> None:
    """`just help` should parse the justfile and exit 0.

    `help` is recipe-only (no shell side effects beyond grep/awk), so it
    is the cheapest way to assert the file parses cleanly.
    """
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        f"`just help` failed (rc={result.returncode}):\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # Sanity: a few key targets should appear in help output.
    for target in ("test", "frontend-install", "frontend-build", "build", "ci"):
        assert target in result.stdout, f"target '{target}' missing from `just help` output"


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_makefile_dry_run_test_target() -> None:
    """`just --show test` should dry-run-render the test recipe without errors.

    `--show` prints the recipe without executing its commands. The rendered
    text must still contain the selected pytest invocation.
    """
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "test"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        f"`just --show test` failed (rc={result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # Recipe should mention pytest somewhere.
    assert "pytest" in result.stdout, (
        f"`just --show test` did not render a pytest invocation:\n{result.stdout}"
    )


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_makefile_run_target_dry_runs_and_invokes_ui() -> None:
    """`just --show run` should reference frontend-build and the UI entry point.

    `just run` is the user-facing "just run the labeler" target —
    distinct from `just dev` (which expects Vite on :5173). It must:
    - Ensure the SPA bundle exists (depend on / call `frontend-build`).
    - Launch `pdomain-ocr-labeler-ui` without `--reload` and without
      `--frontend-dev` (we are SERVING the bundle, not developing it).

    Asserting on the dry-run output keeps the test fast and lets us
    catch accidental regressions like dropping the dependency or
    flipping `--reload` back on.
    """
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "run"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        f"`just --show run` failed (rc={result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    out = result.stdout
    # The displayed recipe must retain its frontend-build call.
    assert "frontend-build" in out or "Building frontend" in out, (
        f"`just --show run` should ensure the SPA is built before serving:\n{out}"
    )
    assert "pdomain-ocr-labeler-ui" in out, f"`just --show run` should launch pdomain-ocr-labeler-ui:\n{out}"
    # Must NOT enable reload or frontend-dev — those are `just dev`'s job.
    assert "--reload" not in out, f"`just run` must not enable --reload:\n{out}"
    assert "--frontend-dev" not in out, f"`just run` must not enable --frontend-dev:\n{out}"


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_makefile_help_lists_run_target() -> None:
    """`just help` should advertise the `run` target alongside `dev`."""
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert any(line.strip() == "run" for line in result.stdout.splitlines()), (
        f"`run` target missing from help output:\n{result.stdout}"
    )


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_makefile_public_recipes_declared() -> None:
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--summary"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    declared = set(result.stdout.split())
    required = {
        "build",
        "openapi-export",
        "format",
        "help",
        "setup",
        "local-frontend-test",
        "ci",
        "frontend-test",
        "run",
        "frontend-dev",
        "test",
        "frontend-install",
        "lint",
        "frontend-build",
        "clean",
    }
    assert not (required - declared), f"Public recipes missing: {sorted(required - declared)}"


def test_local_frontend_test_uses_wrapper_script() -> None:
    """The local frontend test path must isolate test-time sibling resolution."""
    text = JUSTFILE.read_text(encoding="utf-8")
    assert "local-frontend-test:" in text, "local-frontend-test target missing from justfile."
    assert "./scripts/local-frontend-test.sh" in text, (
        "local-frontend-test must run the wrapper that installs pdomain-ui as file: for Vitest."
    )


def test_local_frontend_test_script_restores_link_overlay() -> None:
    """The wrapper should leave package metadata and local links as it found them."""
    script = REPO_ROOT / "scripts" / "local-frontend-test.sh"
    text = script.read_text(encoding="utf-8")
    assert "@pdomain/pdomain-ui@file:../../pdomain-ui" in text, (
        "local frontend tests must use file: pdomain-ui so pnpm resolves React peers from the app."
    )
    for filename in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"):
        assert filename in text, f"local-frontend-test.sh must snapshot and restore {filename}."
    assert "local-frontend-install.sh" in text, (
        "local-frontend-test.sh must restore the normal pnpm link overlay after tests."
    )


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_ci_calls_pre_commit_check() -> None:
    """`just ci` must invoke pre-commit-check so hooks run in CI."""
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "ci"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"`just --show ci` failed (rc={result.returncode}):\n{result.stderr}"
    assert "pre-commit-check" in result.stdout, (
        f"`just ci` does not call pre-commit-check (pre-commit run --all-files):\n{result.stdout}"
    )
    hook = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "pre-commit-check"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert hook.returncode == 0, hook.stderr
    assert "pre-commit run --all-files" in hook.stdout, hook.stdout


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_ci_calls_openapi_export_before_frontend_build() -> None:
    """`just ci` must call openapi-export before frontend-build."""
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "ci"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"`just --show ci` failed (rc={result.returncode}):\n{result.stderr}"
    out = result.stdout
    assert "openapi-export" in out, f"ci does not call openapi-export: {out}"
    build = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "build"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert build.returncode == 0, build.stderr
    assert "frontend-build" in build.stdout, f"build must run frontend-build: {build.stdout}"
    commands = [line.strip().split() for line in out.splitlines() if "just --quiet" in line]
    steps = [step for command in commands for step in command[2:]]
    assert steps.index("openapi-export") < steps.index("build"), (
        f"openapi-export must run before build invokes frontend-build: {out}"
    )


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_ci_runs_frontend_install_before_pre_commit_check() -> None:
    """`just ci` must run frontend-install before pre-commit-check.

    Issue #279: the frontend pre-commit hooks (frontend-tsc, frontend-eslint,
    frontend-prettier) invoke `npm run` / `npx`, which fail with
    `tsc/eslint/prettier not found` if node_modules does not exist.
    Running frontend-install first ensures node_modules is populated
    before pre-commit-check fires the hooks.
    """
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "ci"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "frontend-install" in out, f"frontend-install missing from ci: {out}"
    assert "pre-commit-check" in out, f"pre-commit-check missing from ci: {out}"
    assert out.index("frontend-install") < out.index("pre-commit-check"), (
        f"frontend-install must run before pre-commit-check: {out}"
    )


def test_makefile_mise_download_pins_version() -> None:
    """mise-download target must fetch mise from a pinned, immutable GitHub release URL.

    ``curl https://mise.run | sh`` floats to whatever mise.run currently
    serves — a compromised CDN or DNS-spoofed origin can inject arbitrary
    code. Option-B fix: pin to a specific tagged GitHub release asset URL
    (github.com/jdx/mise/releases/download/<tag>/install.sh). GitHub
    release assets are immutable once a tag is published; TLS provides
    transport integrity. Upstream (jdx/mise) does publish install.sh in
    each release, but requiring minisign on developer machines is impractical,
    so the pinned-URL approach is the pragmatic baseline (F-017).

    Comment lines (``# ...``) are excluded from the pipe-to-shell check
    since the comment block may reference the old pattern as context.
    """
    import re

    text = JUSTFILE.read_text()
    # Strip comment-only lines for the floating-URL check; executable
    # recipe lines must not use the mise.run shortlink.
    code_lines = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "https://mise.run" not in code_lines, (
        "justfile mise-download must not use the floating https://mise.run URL "
        "in executable lines — pin to a tagged GitHub release URL instead (F-017 Option B)"
    )
    # Must pin to a versioned GitHub release asset. Accept either a literal
    # version (`v2026.5.15/install.sh`) or a Make-variable form
    # (`$(MISE_INSTALLER_VERSION)/install.sh` with a matching
    # MISE_INSTALLER_VERSION := vX.Y.Z assignment nearby).
    pinned_literal = re.search(r"github\.com/jdx/mise/releases/download/v[\d.]+/install\.sh", text)
    pinned_via_var = re.search(r"MISE_INSTALLER_VERSION\s*:=\s*v[\d.]+", text) and re.search(
        r"github\.com/jdx/mise/releases/download/\$\(MISE_INSTALLER_VERSION\)/install\.sh", text
    )
    assert pinned_literal or pinned_via_var, (
        "justfile mise-download must pin mise installer to a tagged "
        "github.com/jdx/mise/releases/download/<version>/install.sh URL (F-017). "
        "Use either a literal version or a MISE_INSTALLER_VERSION := vX.Y.Z variable."
    )
