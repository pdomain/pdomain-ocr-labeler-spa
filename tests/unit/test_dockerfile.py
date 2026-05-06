"""Shape pins for the Dockerfile + `.dockerignore` landed in iter 14.

Text-grep style — Docker is not available in the devcontainer, so we
don't exec a real `docker build`; we just enforce the structural
invariants that, if broken, would either make the image fail to build
or ship a broken runtime.

Spec: ``specs/15-deployment-dev.md`` §6.
Peer-mirror: ``pd-prep-for-pgdp/Dockerfile``.

Load-bearing invariants (each has a regression here):

* Three named stages — ``spa`` (Node SPA build), ``wheel`` (uv build),
  ``runtime`` (final image). Stage names are pinned because peer
  tooling and ``docker build --target`` consumers read them.
* Node major must match ``mise.toml`` (``node = "24"``). Drift here
  bites first-run dev (Vite v6 needs Node ≥20) and reproducibility.
* Python major must match ``mise.toml`` (``python = "3.13"``) and
  ``pyproject.toml requires-python``.
* The ``spa`` → ``wheel`` ``COPY --from=spa`` lands at
  ``src/pd_ocr_labeler_spa/static/`` — the exact path
  ``build_hooks/spa_check.py`` checks for ``index.html``. If this
  drifts, ``uv build --wheel`` in the ``wheel`` stage fails (good
  failure mode, but the test catches it pre-build).
* The runtime ``ENTRYPOINT``/``CMD`` invokes the canonical console
  script from ``[project.scripts]`` (``pd-ocr-labeler-ui``).
* ``EXPOSE 8080`` matches the labeler's default port (specs/15 §3).
* ``.dockerignore`` exists and excludes the obvious local-noise paths
  (``.git``, ``__pycache__``, ``frontend/node_modules``, ``.venv``)
  so we don't accidentally inflate the build context or leak local
  state into the image.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
MISE_TOML = REPO_ROOT / "mise.toml"
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"


# ---------------------------------------------------------------------------
# Existence + parse
# ---------------------------------------------------------------------------


def test_dockerfile_exists() -> None:
    assert DOCKERFILE.is_file(), "Dockerfile missing at repo root"


def test_dockerignore_exists() -> None:
    assert DOCKERIGNORE.is_file(), ".dockerignore missing at repo root"


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _from_lines() -> list[str]:
    """Return only the FROM directives — case-insensitive Docker keyword."""
    return [
        line.strip() for line in _dockerfile_text().splitlines() if line.strip().lower().startswith("from ")
    ]


# ---------------------------------------------------------------------------
# Stage names — pinned because docker build --target and our own COPY
# --from references depend on them.
# ---------------------------------------------------------------------------


def test_dockerfile_has_three_named_stages() -> None:
    froms = _from_lines()
    assert len(froms) == 3, f"expected 3 FROM directives, got {len(froms)}: {froms}"


def test_stage_names_are_spa_wheel_runtime() -> None:
    """Stage names are part of the contract — peer tooling
    (``docker build --target wheel``, CI, the Makefile docker targets)
    references them by name. Renaming a stage is a breaking change."""
    froms = _from_lines()
    # Each FROM should end with `AS <name>` (case-insensitive).
    aliases: list[str] = []
    for line in froms:
        m = re.search(r"\bAS\s+(\w+)\s*$", line, re.IGNORECASE)
        assert m is not None, f"FROM line missing `AS <name>`: {line!r}"
        aliases.append(m.group(1).lower())
    assert aliases == ["spa", "wheel", "runtime"], (
        f"stage names must be exactly [spa, wheel, runtime] in order, got {aliases}"
    )


# ---------------------------------------------------------------------------
# Base image versions must agree with mise.toml
# ---------------------------------------------------------------------------


def _mise_versions() -> dict[str, str]:
    text = MISE_TOML.read_text(encoding="utf-8")
    versions: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r'\s*(\w+)\s*=\s*"([^"]+)"', line)
        if m:
            versions[m.group(1)] = m.group(2)
    return versions


def test_spa_stage_uses_node_major_matching_mise() -> None:
    node_major = _mise_versions()["node"]
    froms = _from_lines()
    spa_from = next(line for line in froms if re.search(r"\bAS\s+spa\b", line, re.IGNORECASE))
    # node:24-bookworm-slim, node:24-slim, node:24-alpine — all start with `node:24`.
    assert re.search(rf"\bnode:{re.escape(node_major)}(\b|[-.])", spa_from), (
        f"spa stage base image must use node:{node_major}* "
        f'(matching mise.toml node = "{node_major}"); got: {spa_from!r}'
    )


def test_wheel_and_runtime_use_python_major_matching_mise() -> None:
    py_major = _mise_versions()["python"]
    froms = _from_lines()
    py_pattern = re.compile(rf"\bpython:{re.escape(py_major)}(\b|[-.])")
    for alias in ("wheel", "runtime"):
        line = next(line for line in froms if re.search(rf"\bAS\s+{alias}\b", line, re.IGNORECASE))
        assert py_pattern.search(line), (
            f"{alias} stage base image must use python:{py_major}* "
            f'(matching mise.toml python = "{py_major}"); got: {line!r}'
        )


# ---------------------------------------------------------------------------
# spa → wheel handoff: SPA bundle must land where the build hook expects.
# ---------------------------------------------------------------------------


def test_copy_from_spa_lands_in_static_dir_before_uv_build() -> None:
    """``build_hooks/spa_check.py`` looks for
    ``src/pd_ocr_labeler_spa/static/index.html``. If the COPY target
    drifts, the wheel build either fails (loud) or silently ships a
    blank app (depending on ``PD_LABELER_SKIP_SPA_CHECK``). Pin the
    target path explicitly."""
    text = _dockerfile_text()
    # The COPY --from=spa instruction must reference the static/ dir.
    pattern = re.compile(
        r"COPY\s+--from=spa\s+\S+\s+\./?src/pd_ocr_labeler_spa/static/?",
        re.IGNORECASE,
    )
    assert pattern.search(text), (
        "Dockerfile must contain `COPY --from=spa <src> ./src/pd_ocr_labeler_spa/static/` "
        "so the wheel build hook can find static/index.html."
    )


def test_wheel_stage_runs_uv_build() -> None:
    """The wheel stage must actually invoke ``uv build`` — without it,
    the runtime stage's ``COPY --from=wheel /dist/*.whl`` finds nothing
    and the image build fails."""
    text = _dockerfile_text()
    # Allow any flag ordering, but `uv build` with --wheel and -o /dist must appear.
    assert re.search(r"\buv\s+build\b", text), "wheel stage must run `uv build`"
    assert "--wheel" in text, "uv build must use --wheel (sdist won't ship the SPA)"
    assert "/dist/" in text or "/dist " in text, "uv build must output to /dist/ for runtime COPY"


# ---------------------------------------------------------------------------
# Runtime stage: entrypoint + port
# ---------------------------------------------------------------------------


def _console_script_name() -> str:
    """Read the canonical entrypoint name from pyproject.toml so the
    test tracks the source of truth, not a hardcoded string."""
    with PYPROJECT_TOML.open("rb") as fh:
        data = tomllib.load(fh)
    scripts = data["project"]["scripts"]
    # specs/15 §2 names `pd-ocr-labeler-ui` as the canonical end-user
    # entrypoint. Other scripts may exist later; this one is the one
    # the container should boot.
    assert "pd-ocr-labeler-ui" in scripts, (
        "pyproject.toml [project.scripts] must declare pd-ocr-labeler-ui (specs/15-deployment-dev.md §2)."
    )
    return "pd-ocr-labeler-ui"


def test_runtime_entrypoint_invokes_console_script() -> None:
    name = _console_script_name()
    text = _dockerfile_text()
    # Either ENTRYPOINT or CMD is fine — both produce the same boot.
    pattern = re.compile(rf'(ENTRYPOINT|CMD)\s+\[\s*"{re.escape(name)}"', re.IGNORECASE)
    assert pattern.search(text), (
        f"Dockerfile must set ENTRYPOINT or CMD to invoke the {name!r} console script."
    )


def test_runtime_exposes_port_8080() -> None:
    """8080 is the labeler's default port (specs/15 §3). The container
    must EXPOSE it so `docker run -P` wires the host port automatically
    and so image-introspection tooling sees the correct port."""
    text = _dockerfile_text()
    assert re.search(r"^EXPOSE\s+8080\b", text, re.MULTILINE), "Dockerfile must EXPOSE 8080"


def test_runtime_binds_host_to_all_interfaces() -> None:
    """Inside a container, listening on 127.0.0.1 makes the port
    unreachable from outside the container. The entrypoint or env vars
    must set the host to 0.0.0.0."""
    text = _dockerfile_text()
    has_arg = "--host" in text and "0.0.0.0" in text
    has_env = re.search(r"PD_LABELER_HOST\s*=\s*0\.0\.0\.0", text) is not None
    assert has_arg or has_env, (
        "Runtime must bind to 0.0.0.0 (either via `--host 0.0.0.0` in "
        "ENTRYPOINT/CMD or via `ENV PD_LABELER_HOST=0.0.0.0`)."
    )


# ---------------------------------------------------------------------------
# .dockerignore: keep build context lean and don't leak local state.
# ---------------------------------------------------------------------------


def test_dockerignore_excludes_essential_paths() -> None:
    """A missing `.dockerignore` rule for `.git/` or `node_modules/`
    silently inflates the build context (slow builds, leaked secrets).
    Pin the must-have entries; leave room for future additions."""
    lines = {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    required = {
        ".git/",
        "__pycache__/",
        ".venv/",
        "frontend/node_modules/",
    }
    missing = required - lines
    assert not missing, f".dockerignore missing required entries: {sorted(missing)}"
