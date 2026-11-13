"""Smoke tests for the justfile's `docker-*` targets.

These targets are thin wrappers around `docker build` / `docker run`,
so the value here is not in re-testing docker — it's in ensuring the
three-way contract between Settings, Dockerfile EXPOSE, and the
justfile's `-p` flag stays consistent. A drift between any of them
would surface as a "the labeler runs but I can't reach it" bug, which
is annoying enough to warrant a hard pin.

Strategy: dry-run-render each docker target so we exercise the parser
and variable expansion (mirroring `test_makefile.py`), then introspect
`Settings().port` and grep the Dockerfile's `EXPOSE` line and the
justfile's `docker-run` recipe — all three must agree.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = REPO_ROOT / "justfile"
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _have_just() -> bool:
    return shutil.which("just") is not None


def _make_dry_run(target: str) -> subprocess.CompletedProcess[str]:
    # --show prints the recipe without executing its AI wrapper.
    return subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--show", target],
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Parse / dry-run — every target must render cleanly under `just --show`.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
@pytest.mark.parametrize("target", ["docker-build", "docker-run", "docker-shell"])
def test_docker_target_dry_runs_cleanly(target: str) -> None:
    """`just --show <target>` must parse + render without error.

    A typo in the recipe (or a missing dependency target) would surface
    here without needing docker installed — the dry-run only resolves
    variables and prints the recipe."""
    result = _make_dry_run(target)
    assert result.returncode == 0, (
        f"`just --show {target}` failed (rc={result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_docker_targets_appear_in_help() -> None:
    """`just help` must list all three docker-* targets (each has `## …`)."""
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    for target in ("docker-build", "docker-run", "docker-shell"):
        assert target in result.stdout, f"target '{target}' missing from `just help`"


# ---------------------------------------------------------------------------
# Image-tag pin — the default tag must be the canonical one.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
@pytest.mark.parametrize("target", ["docker-build", "docker-run", "docker-shell"])
def test_docker_targets_use_default_image_tag(target: str) -> None:
    """All three targets must reference the same default image tag.

    The default is `pdomain-ocr-labeler-spa:dev` (matches pdomain-prep-for-pgdp's
    `pgdp-prep:dev` shape). Operators can override via
    `DOCKER_IMAGE=… DOCKER_TAG=… just docker-build`, but the default
    must be stable so muscle-memory works.
    """
    result = _make_dry_run(target)
    assert result.returncode == 0
    assert "pdomain-ocr-labeler-spa:dev" in result.stdout or (
        "${DOCKER_IMAGE:-pdomain-ocr-labeler-spa}" in result.stdout and "${DOCKER_TAG:-dev}" in result.stdout
    ), f"`just --show {target}` did not reference default tag pdomain-ocr-labeler-spa:dev:\n{result.stdout}"


# ---------------------------------------------------------------------------
# Port-alignment three-way check (Settings ↔ Dockerfile EXPOSE ↔ justfile -p).
# ---------------------------------------------------------------------------


def _dockerfile_expose_port() -> int:
    """Return the (single) port the Dockerfile EXPOSEs."""
    text = DOCKERFILE.read_text()
    matches = re.findall(r"^EXPOSE\s+(\d+)\b", text, re.MULTILINE)
    assert len(matches) == 1, f"Dockerfile must declare exactly one EXPOSE line; found {matches!r}"
    return int(matches[0])


def test_settings_port_matches_dockerfile_expose() -> None:
    """`Settings().port` is what `pdomain-ocr-labeler-ui` binds to inside
    the container; the Dockerfile EXPOSE line documents that port for
    `docker run -P` and image-introspection tools. The two must agree
    or `docker run -P` maps the wrong port and the labeler is
    unreachable from the host.
    """
    from pdomain_ocr_labeler_spa.settings import Settings

    assert Settings().port == _dockerfile_expose_port(), (
        "Settings().port and Dockerfile EXPOSE must match. "
        f"Settings().port={Settings().port!r}, EXPOSE={_dockerfile_expose_port()!r}"
    )


@pytest.mark.skipif(not _have_just(), reason="`just` not on PATH")
def test_docker_run_maps_settings_port_into_container() -> None:
    """`just docker-run`'s `-p HOST:CONTAINER` flag must end with the
    same container port the Dockerfile EXPOSEs (which equals
    `Settings().port`). If the justfile's container-side port drifts
    from EXPOSE, the host port maps to nothing.
    """
    from pdomain_ocr_labeler_spa.settings import Settings

    expected = Settings().port
    result = _make_dry_run("docker-run")
    assert result.returncode == 0

    # Find every `-p HOST:CONTAINER` token in the rendered recipe.
    # Container side may be a literal int or a shell-variable expansion that
    # already got resolved by `-n`.
    matches = re.findall(r"-p\s+\S+:(\d+)\b", result.stdout)
    assert matches, f"`just --show docker-run` rendered no `-p HOST:CONTAINER` flag:\n{result.stdout}"
    for container_port in matches:
        assert int(container_port) == expected, (
            f"`just docker-run` -p flag's container-side port {container_port} "
            f"does not match Settings().port={expected}"
        )


# ---------------------------------------------------------------------------
# .PHONY coverage — the new targets must be declared phony so an
# accidental file/dir of the same name doesn't shadow the recipe.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# `_docker` macro guard — B-24: terse-fail without docker on PATH.
# ---------------------------------------------------------------------------


def test_makefile_defines_docker_macro() -> None:
    """B-24: the justfile must define a `_docker` macro analogous to `_npm`.

    Without it, `just docker-build` on a host that lacks docker fails
    with bash's terse `make: docker: No such file or directory`. The
    macro adds a `command -v docker` preflight + a friendly options
    block (install Docker Desktop, Colima, devcontainer feature) so
    the contributor experience matches `just frontend-build` without
    npm.
    """
    text = JUSTFILE.read_text()
    assert "_docker +args:" in text, "justfile must define a `_docker` macro (B-24)"
    # The macro must include the command-presence check.
    assert "command -v docker" in text, (
        "`_docker` macro must check for docker on PATH via `command -v docker`"
    )


@pytest.mark.parametrize("target", ["docker-build", "docker-run", "docker-shell"])
def test_docker_targets_invoke_docker_macro(target: str) -> None:
    """All three docker-* recipes must dispatch through `$(call _docker,...)`.

    A target that calls `docker …` directly bypasses the preflight
    and re-introduces B-24. The text-grep is loose enough to allow
    formatting variation but tight enough to catch a regression
    where someone copies a recipe and forgets the macro.
    """
    text = JUSTFILE.read_text()
    # Locate the recipe block for `target`. Each docker target is a
    # single-recipe line in the current justfile, so we just slice
    # between the target line and the next blank line.
    lines = text.splitlines()
    target_line = next(
        (i for i, ln in enumerate(lines) if ln.startswith(f"{target}:")),
        None,
    )
    assert target_line is not None, f"target `{target}` not found in justfile"
    # Recipe lines are tab-indented; collect them until we hit a
    # non-tab non-blank line.
    recipe: list[str] = []
    for ln in lines[target_line + 1 :]:
        if ln.startswith("    "):
            recipe.append(ln)
        elif ln.strip() == "":
            continue
        else:
            break
    recipe_text = "\n".join(recipe)
    assert "_docker" in recipe_text, (
        f"target `{target}` must dispatch through the `_docker` macro (B-24); got recipe:\n{recipe_text}"
    )


def test_docker_recipes_are_public() -> None:
    result = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--summary"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    declared = set(result.stdout.split())
    required = {"docker-run", "docker-shell", "docker-build"}
    assert not (required - declared), f"Public recipes missing: {sorted(required - declared)}"
