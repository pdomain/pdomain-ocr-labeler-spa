"""Tests for deployment scaffold — issue #250.

Covers the five acceptance bullets:
  1. `just setup` invokes uv sync + pre-commit install
  2. `just lint` includes ruff, eslint, and tsc --noEmit
  3. `upgrade-deps` refuses-with-message when dev-local detected
  4. `upgrade-deps-local` recipe writes the .pdomain-dev-local marker
  5. `just build` (via spa_check.py) raises when static/index.html absent
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# uv installs into UV_PROJECT_ENVIRONMENT when set and into .venv otherwise,
# and the justfile guard resolves the marker the same way. Reading the real
# rule here keeps the test honest inside the devcontainer, which names the
# environment ".venv-container".
PROJECT_VENV = REPO_ROOT / (os.environ.get("UV_PROJECT_ENVIRONMENT") or ".venv")
JUSTFILE = REPO_ROOT / "justfile"


def _have_just() -> bool:
    return shutil.which("just") is not None


# ---------------------------------------------------------------------------
# Bullet 1: just setup
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_makefile_setup_invokes_uv_sync() -> None:
    """`just --show setup` must include a `uv sync` invocation."""
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "setup"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"`just --show setup` failed:\n{result.stderr}"
    assert "uv sync" in result.stdout, f"`just --show setup` missing `uv sync`:\n{result.stdout}"


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_makefile_setup_invokes_pre_commit_install() -> None:
    """`just --show setup` must install pre-commit hooks."""
    assert "install-hooks" in subprocess.check_output(
        ["just", "--justfile", str(JUSTFILE), "--show", "setup"], text=True
    )
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "install-hooks"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"`just --show setup` failed:\n{result.stderr}"
    assert "pre-commit install" in result.stdout, (
        f"`just --show setup` missing `pre-commit install`:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# Bullet 2: just lint includes ruff + eslint + tsc --noEmit
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_makefile_lint_includes_ruff() -> None:
    """`just --show lint` must invoke ruff."""
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "lint"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"`just --show lint` failed:\n{result.stderr}"
    assert "ruff" in result.stdout, f"`just --show lint` missing ruff:\n{result.stdout}"


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_makefile_lint_includes_eslint() -> None:
    """`just --show frontend-lint` must invoke eslint (via npm run lint or direct call)."""
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "frontend-lint"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"`just --show lint` failed:\n{result.stderr}"
    assert "eslint" in result.stdout.lower() or "npm" in result.stdout, (
        f"`just --show lint` missing eslint / npm invocation:\n{result.stdout}"
    )


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_makefile_lint_includes_tsc_no_emit() -> None:
    """`just --show frontend-typecheck` must invoke tsc (typecheck / --noEmit)."""
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", "frontend-typecheck"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"`just --show lint` failed:\n{result.stderr}"
    assert "tsc" in result.stdout or "typecheck" in result.stdout or "type-check" in result.stdout, (
        f"`just --show lint` missing tsc / typecheck invocation:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# Bullet 3: upgrade-deps refuses with message
# ---------------------------------------------------------------------------


def _all_recipes() -> set[str]:
    return set(
        subprocess.check_output(
            ["just", "--justfile", str(JUSTFILE), "--summary"],
            text=True,
        ).split()
    )


def test_upgrade_deps_recipe_is_public() -> None:
    """upgrade-deps must be declared in public recipes."""
    text = JUSTFILE.read_text()
    assert "upgrade-deps" in text, "upgrade-deps target missing from justfile"
    assert "upgrade-deps" in _all_recipes(), "upgrade-deps missing from public recipe list"


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_upgrade_deps_refuses_when_pd_dev_local_set() -> None:
    """`just upgrade-deps` must exit non-zero and print a refusal message
    when PDOMAIN_DEV_LOCAL=1 is set in the environment (probe 3 of 3)."""
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "upgrade-deps"],
        capture_output=True,
        text=True,
        timeout=30,
        env={**__import__("os").environ, "PDOMAIN_DEV_LOCAL": "1"},
    )
    assert result.returncode != 0, (
        f"`just upgrade-deps` should exit non-zero when PDOMAIN_DEV_LOCAL=1 "
        f"(exited {result.returncode}):\n{result.stdout}"
    )
    combined = result.stdout + result.stderr
    assert "upgrade-deps-local" in combined or "dev-local" in combined.lower(), (
        f"`just upgrade-deps` refusal message must mention `upgrade-deps-local` or 'dev-local':\n{combined}"
    )


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_upgrade_deps_refuses_when_marker_present() -> None:
    """`just upgrade-deps` must exit non-zero and print a refusal message
    when the .pdomain-dev-local marker exists (probe 2 of 3)."""
    marker = PROJECT_VENV / ".pdomain-dev-local"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    try:
        result = subprocess.run(
            ["just", "--justfile", str(JUSTFILE), "upgrade-deps"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0, (
            f"`just upgrade-deps` should exit non-zero when {marker} exists "
            f"(exited {result.returncode}):\n{result.stdout}"
        )
        combined = result.stdout + result.stderr
        assert "upgrade-deps-local" in combined or "dev-local" in combined.lower(), (
            f"refusal message must mention `upgrade-deps-local` or 'dev-local':\n{combined}"
        )
    finally:
        marker.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Bullet 4: upgrade-deps-local recipe writes the .pdomain-dev-local marker
# ---------------------------------------------------------------------------


def test_upgrade_deps_local_recipe_is_public() -> None:
    """upgrade-deps-local must be declared in public recipes."""
    text = JUSTFILE.read_text()
    assert "upgrade-deps-local" in text, "upgrade-deps-local target missing from justfile"
    assert "upgrade-deps-local" in _all_recipes(), "upgrade-deps-local missing from public recipe list"


def test_upgrade_deps_local_recipe_writes_pd_dev_local_marker() -> None:
    """The upgrade-deps-local recipe must contain a command that writes
    the .pdomain-dev-local marker file."""
    text = JUSTFILE.read_text()
    assert ".pdomain-dev-local" in text, (
        "justfile upgrade-deps-local recipe must write the .pdomain-dev-local marker"
    )


# ---------------------------------------------------------------------------
# Bullet 5: just build raises when static/index.html absent
# ---------------------------------------------------------------------------


def _load_spa_check_module() -> types.ModuleType:
    """Load build_hooks/spa_check.py with hatchling mocked out."""
    import importlib.util
    import sys

    # Provide a minimal BuildHookInterface stub so the hook module imports
    # cleanly without requiring hatchling in the test venv.
    fake_hatchling = types.ModuleType("hatchling")
    fake_builders = types.ModuleType("hatchling.builders")
    fake_hooks = types.ModuleType("hatchling.builders.hooks")
    fake_plugin = types.ModuleType("hatchling.builders.hooks.plugin")
    fake_iface = types.ModuleType("hatchling.builders.hooks.plugin.interface")

    class _FakeBuildHookInterface:
        PLUGIN_NAME = ""

        def initialize(self, version: str, build_data: dict) -> None:
            pass

    fake_iface.BuildHookInterface = _FakeBuildHookInterface  # type: ignore[attr-defined]

    for mod_name, mod in [
        ("hatchling", fake_hatchling),
        ("hatchling.builders", fake_builders),
        ("hatchling.builders.hooks", fake_hooks),
        ("hatchling.builders.hooks.plugin", fake_plugin),
        ("hatchling.builders.hooks.plugin.interface", fake_iface),
    ]:
        sys.modules.setdefault(mod_name, mod)

    hook_path = REPO_ROOT / "build_hooks" / "spa_check.py"
    spec = importlib.util.spec_from_file_location("spa_check_test", hook_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_spa_check_hook_raises_when_index_html_absent() -> None:
    """SpaBundleCheckHook.initialize must raise RuntimeError when
    static/index.html is absent (or empty) for wheel builds."""
    from unittest.mock import MagicMock

    module = _load_spa_check_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        hook = object.__new__(module.SpaBundleCheckHook)  # type: ignore[attr-defined]
        hook.root = tmpdir
        hook.target_name = "wheel"
        hook.config = {}
        hook.build_config = MagicMock()
        hook.app = MagicMock()

        with pytest.raises(RuntimeError, match="SPA bundle"):
            hook.initialize("standard", {})


def test_spa_check_hook_skips_for_editable_install() -> None:
    """SpaBundleCheckHook.initialize must not raise for editable installs
    even when static/index.html is absent."""
    from unittest.mock import MagicMock

    module = _load_spa_check_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        hook = object.__new__(module.SpaBundleCheckHook)  # type: ignore[attr-defined]
        hook.root = tmpdir
        hook.target_name = "wheel"
        hook.config = {}
        hook.build_config = MagicMock()
        hook.app = MagicMock()
        # editable version → should not raise
        hook.initialize("editable", {})


def test_frontend_package_json_has_lint_script() -> None:
    """frontend/package.json must declare a `lint` npm script."""
    import json

    pkg = REPO_ROOT / "frontend" / "package.json"
    data = json.loads(pkg.read_text())
    scripts = data.get("scripts", {})
    assert "lint" in scripts, (
        "frontend/package.json missing `lint` script (needed for `just lint` to run eslint)"
    )


def test_frontend_package_json_has_typecheck_script() -> None:
    """frontend/package.json must declare a `typecheck` npm script."""
    import json

    pkg = REPO_ROOT / "frontend" / "package.json"
    data = json.loads(pkg.read_text())
    scripts = data.get("scripts", {})
    assert "typecheck" in scripts, (
        "frontend/package.json missing `typecheck` script (needed for `just lint` tsc --noEmit)"
    )


def test_frontend_has_eslint_config() -> None:
    """frontend/ must contain an eslint.config.js or eslint.config.ts."""
    frontend = REPO_ROOT / "frontend"
    configs = list(frontend.glob("eslint.config.*"))
    assert configs, "frontend/ missing eslint.config.js / eslint.config.ts"
