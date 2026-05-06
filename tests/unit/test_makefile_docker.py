"""Smoke tests for the Makefile's `docker-*` targets.

These targets are thin wrappers around `docker build` / `docker run`,
so the value here is not in re-testing docker — it's in ensuring the
three-way contract between Settings, Dockerfile EXPOSE, and the
Makefile's `-p` flag stays consistent. A drift between any of them
would surface as a "the labeler runs but I can't reach it" bug, which
is annoying enough to warrant a hard pin.

Strategy: dry-run-render each docker target so we exercise the parser
and variable expansion (mirroring `test_makefile.py`), then introspect
`Settings().port` and grep the Dockerfile's `EXPOSE` line and the
Makefile's `docker-run` recipe — all three must agree.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _have_make() -> bool:
    return shutil.which("make") is not None


def _make_dry_run(target: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "-C", str(REPO_ROOT), "-n", target],
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Parse / dry-run — every target must render cleanly under `make -n`.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
@pytest.mark.parametrize("target", ["docker-build", "docker-run", "docker-shell"])
def test_docker_target_dry_runs_cleanly(target: str) -> None:
    """`make -n <target>` must parse + render without error.

    A typo in the recipe (or a missing dependency target) would surface
    here without needing docker installed — the dry-run only resolves
    variables and prints the recipe."""
    result = _make_dry_run(target)
    assert result.returncode == 0, (
        f"`make -n {target}` failed (rc={result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_docker_targets_appear_in_help() -> None:
    """`make help` must list all three docker-* targets (each has `## …`)."""
    result = subprocess.run(
        ["make", "-C", str(REPO_ROOT), "help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    for target in ("docker-build", "docker-run", "docker-shell"):
        assert target in result.stdout, f"target '{target}' missing from `make help`"


# ---------------------------------------------------------------------------
# Image-tag pin — the default tag must be the canonical one.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
@pytest.mark.parametrize("target", ["docker-build", "docker-run", "docker-shell"])
def test_docker_targets_use_default_image_tag(target: str) -> None:
    """All three targets must reference the same default image tag.

    The default is `pd-ocr-labeler-spa:dev` (matches pd-prep-for-pgdp's
    `pgdp-prep:dev` shape). Operators can override via
    `make docker-build DOCKER_IMAGE=… DOCKER_TAG=…`, but the default
    must be stable so muscle-memory works.
    """
    result = _make_dry_run(target)
    assert result.returncode == 0
    assert "pd-ocr-labeler-spa:dev" in result.stdout, (
        f"`make -n {target}` did not reference default tag pd-ocr-labeler-spa:dev:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# Port-alignment three-way check (Settings ↔ Dockerfile EXPOSE ↔ Makefile -p).
# ---------------------------------------------------------------------------


def _dockerfile_expose_port() -> int:
    """Return the (single) port the Dockerfile EXPOSEs."""
    text = DOCKERFILE.read_text()
    matches = re.findall(r"^EXPOSE\s+(\d+)\b", text, re.MULTILINE)
    assert len(matches) == 1, f"Dockerfile must declare exactly one EXPOSE line; found {matches!r}"
    return int(matches[0])


def test_settings_port_matches_dockerfile_expose() -> None:
    """`Settings().port` is what `pd-ocr-labeler-ui` binds to inside
    the container; the Dockerfile EXPOSE line documents that port for
    `docker run -P` and image-introspection tools. The two must agree
    or `docker run -P` maps the wrong port and the labeler is
    unreachable from the host.
    """
    from pd_ocr_labeler_spa.settings import Settings

    assert Settings().port == _dockerfile_expose_port(), (
        "Settings().port and Dockerfile EXPOSE must match. "
        f"Settings().port={Settings().port!r}, EXPOSE={_dockerfile_expose_port()!r}"
    )


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
def test_docker_run_maps_settings_port_into_container() -> None:
    """`make docker-run`'s `-p HOST:CONTAINER` flag must end with the
    same container port the Dockerfile EXPOSEs (which equals
    `Settings().port`). If the Makefile's container-side port drifts
    from EXPOSE, the host port maps to nothing.
    """
    from pd_ocr_labeler_spa.settings import Settings

    expected = Settings().port
    result = _make_dry_run("docker-run")
    assert result.returncode == 0

    # Find every `-p HOST:CONTAINER` token in the rendered recipe.
    # Container side may be a literal int or a make-var expansion that
    # already got resolved by `-n`.
    matches = re.findall(r"-p\s+\S+:(\d+)\b", result.stdout)
    assert matches, f"`make -n docker-run` rendered no `-p HOST:CONTAINER` flag:\n{result.stdout}"
    for container_port in matches:
        assert int(container_port) == expected, (
            f"`make docker-run` -p flag's container-side port {container_port} "
            f"does not match Settings().port={expected}"
        )


# ---------------------------------------------------------------------------
# .PHONY coverage — the new targets must be declared phony so an
# accidental file/dir of the same name doesn't shadow the recipe.
# ---------------------------------------------------------------------------


def test_docker_targets_are_phony() -> None:
    text = MAKEFILE.read_text()
    # Reuse the loose "first .PHONY block" parse from test_makefile.py.
    phony_block: list[str] = []
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

    declared: set[str] = set()
    for chunk in phony_block:
        for tok in chunk.replace("\\", " ").split():
            declared.add(tok)

    must_be_phony = {"docker-build", "docker-run", "docker-shell"}
    missing = must_be_phony - declared
    assert not missing, f"docker targets missing from .PHONY: {sorted(missing)}"
