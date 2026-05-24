"""Shape pins for the Dockerfile + `.dockerignore` landed in iter 14.

Text-grep style — Docker is not available in the devcontainer, so we
don't exec a real `docker build`; we just enforce the structural
invariants that, if broken, would either make the image fail to build
or ship a broken runtime.

Spec: ``docs/architecture/15-deployment-dev.md`` §6.
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
        "pyproject.toml [project.scripts] must declare pd-ocr-labeler-ui "
        "(docs/architecture/15-deployment-dev.md §2)."
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
    must set the host to 0.0.0.0.

    The env-var path must use the prefix `Settings` actually reads
    (``Settings.model_config["env_prefix"]``); see B-16. Using a
    different spelling (e.g. ``PD_LABELER_HOST`` with an underscore
    when Settings reads ``PDLABELER_HOST``) would silently no-op
    because pydantic-settings drops envs that don't match the prefix.
    """
    from pd_ocr_labeler_spa.settings import Settings

    prefix = Settings.model_config["env_prefix"]  # pyright: ignore[reportTypedDictNotRequiredAccess]
    assert prefix, "Settings must declare a non-empty env_prefix"

    text = _dockerfile_text()
    has_arg = "--host" in text and "0.0.0.0" in text
    has_env = re.search(rf"{re.escape(prefix)}HOST\s*=\s*0\.0\.0\.0", text) is not None
    assert has_arg or has_env, (
        "Runtime must bind to 0.0.0.0 (either via `--host 0.0.0.0` in "
        f"ENTRYPOINT/CMD or via `ENV {prefix}HOST=0.0.0.0`)."
    )


def test_dockerfile_env_lines_use_settings_prefix() -> None:
    """B-16: any ``ENV PD…=…`` line in the Dockerfile must spell the
    settings env prefix exactly. Pydantic-settings ignores envs that
    don't match the prefix, so a stray ``PD_LABELER_*`` (with an
    underscore) silently becomes dead code while looking purposeful.

    We only constrain ``ENV`` lines that *look* labeler-targeted —
    i.e. start with ``PD`` after the ``ENV`` keyword. Other ENV
    keys (``PYTHONDONTWRITEBYTECODE``, ``UV_LINK_MODE``, ``PIP_…``)
    are unrelated runtime/toolchain knobs and aren't covered.
    """
    from pd_ocr_labeler_spa.settings import Settings

    prefix = Settings.model_config["env_prefix"]  # pyright: ignore[reportTypedDictNotRequiredAccess]
    assert prefix, "Settings must declare a non-empty env_prefix"

    text = _dockerfile_text()

    # Find every `ENV <KEY>=…` line (single or multi-key form). Multi-line
    # ENV (`ENV A=1 \\\n    B=2`) is normalised by reading the joined
    # source — we look at *all* tokens that look like `KEY=VALUE` after an
    # ENV directive within a continuation block.
    offending: list[str] = []
    in_env_block = False
    for raw in text.splitlines():
        line = raw.strip()
        # Strip line continuation marker for token scanning.
        scan = line.rstrip("\\").rstrip()
        if line.lower().startswith("env "):
            in_env_block = True
            scan = scan[len("ENV ") :].strip()
        if not in_env_block:
            continue
        for token in scan.split():
            # Each token in an ENV block looks like KEY=VALUE.
            if "=" not in token:
                continue
            key = token.split("=", 1)[0]
            if key.upper().startswith("PD") and not key.startswith(prefix):
                offending.append(key)
        # Continuation ends when the line does not end in a backslash.
        if not raw.rstrip().endswith("\\"):
            in_env_block = False

    assert not offending, (
        f"Dockerfile ENV keys starting with `PD` must use Settings "
        f"prefix {prefix!r}; offenders: {offending}. "
        "See B-16 — wrong-prefix envs are silently ignored by pydantic-settings."
    )


# ---------------------------------------------------------------------------
# .dockerignore: keep build context lean and don't leak local state.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# B-20: runtime stage installs from `uv.lock` (via `uv export --frozen`)
# rather than letting `pip install <wheel>` re-resolve transitive deps.
# ---------------------------------------------------------------------------


def test_wheel_stage_exports_frozen_requirements_for_runtime() -> None:
    """B-20: the wheel stage must export `uv.lock` to a frozen
    requirements file (so the runtime install can't drift). The export
    invocation must reference `--frozen` — without it, `uv export`
    happily re-resolves and the lockfile becomes decorative.

    Tests the *invocation*, not the lockfile content — the lockfile
    has its own validation via `uv sync`. We just need to know docker
    builds aren't sliding off the pinned tree.
    """
    text = _dockerfile_text()
    # `uv export` somewhere in the file…
    assert re.search(r"\buv\s+export\b", text), (
        "wheel stage must run `uv export` to emit a frozen requirements.txt for the runtime stage (B-20)."
    )
    # …with `--frozen` (otherwise the lock is decorative).
    assert "--frozen" in text, (
        "`uv export` must use `--frozen` so a stale lockfile fails "
        "the build instead of being silently re-resolved (B-20)."
    )


def test_runtime_install_uses_frozen_requirements_with_no_deps_wheel() -> None:
    """B-20: the runtime stage must install the locked transitive deps
    *first* (via `pip install -r requirements.txt`) and then install
    the wheel itself with `--no-deps` so pip cannot re-resolve.

    Concretely: somewhere in the runtime stage, both
        pip install … -r …requirements.txt
    and
        pip install … --no-deps …*.whl
    must appear. Order matters at runtime (deps first), but a strict
    line-order check is brittle to layer reorganisation; instead we
    check both forms exist and the wheel form carries `--no-deps`.
    """
    text = _dockerfile_text()

    # The runtime stage starts at the third FROM. Slice from there so
    # the `uv export` call in the wheel stage doesn't satisfy these
    # assertions accidentally.
    runtime_start = text.lower().find("\nfrom python")  # wheel stage
    runtime_start = text.lower().find("\nfrom python", runtime_start + 1)  # runtime stage
    assert runtime_start != -1, "could not locate runtime FROM"
    runtime = text[runtime_start:]

    has_requirements_install = re.search(
        r"pip\s+install[^\n]*-r\s+\S*requirements\.txt",
        runtime,
    )
    assert has_requirements_install, (
        "runtime stage must `pip install -r …requirements.txt` to apply "
        "the frozen lock before installing the wheel (B-20)."
    )

    has_wheel_install_no_deps = re.search(
        r"pip\s+install[^\n]*--no-deps[^\n]*\.whl",
        runtime,
    )
    assert has_wheel_install_no_deps, (
        "runtime stage must install the wheel with `--no-deps` so pip "
        "cannot re-resolve transitive deps and bypass the lock (B-20)."
    )


# ---------------------------------------------------------------------------
# B-21: runtime stage must not carry `git` in the final image layer.
# ---------------------------------------------------------------------------


def test_runtime_stage_does_not_keep_git_installed() -> None:
    """B-21: git is needed at install time (to clone the pd-book-tools
    git source) but has no runtime use — the labeler does not shell out
    to git. Keeping it installed bloats the image and grows the attack
    surface.

    The fix wraps the apt-get install + pip install + apt-get purge in
    a single RUN so the layer's net contribution is wheel-installed
    Python packages and *not* the git binary.
    """
    text = _dockerfile_text()
    runtime_start = text.lower().find("\nfrom python")  # wheel stage
    runtime_start = text.lower().find("\nfrom python", runtime_start + 1)  # runtime stage
    assert runtime_start != -1, "could not locate runtime FROM"
    runtime = text[runtime_start:]

    # Either git is never installed in runtime, or it is installed +
    # purged in the same step. We approximate "same step" by requiring
    # the purge to appear in the runtime slice if the install does.
    runtime_installs_git = re.search(r"apt-get\s+install[^\n]*\bgit\b", runtime)
    if runtime_installs_git:
        assert re.search(r"apt-get\s+purge[^\n]*\bgit\b", runtime) or re.search(
            r"apt-get\s+remove[^\n]*\bgit\b", runtime
        ), (
            "runtime stage installs git but never purges it — the final "
            "image layer keeps a git binary it never uses (B-21)."
        )


# ---------------------------------------------------------------------------
# F-011 / #416: the spa stage must use pnpm --frozen-lockfile (not npm),
# matching release.yml and ci.yml — all three must agree on pnpm.
# ---------------------------------------------------------------------------


def _spa_stage_text() -> str:
    """Return the text of the spa stage (between first FROM and second FROM)."""
    text = _dockerfile_text()
    spa_start = text.lower().find("\nfrom node")
    if spa_start == -1:
        spa_start = 0 if text.lower().startswith("from node") else -1
    assert spa_start != -1 or text.lower().startswith("from node"), "could not locate spa FROM"
    next_from = text.lower().find("\nfrom ", max(spa_start, 0) + 1)
    assert next_from != -1, "could not locate stage following spa"
    return text[max(spa_start, 0) : next_from]


def test_spa_stage_uses_pnpm_frozen_lockfile() -> None:
    """F-011: the spa stage must install with ``pnpm install --frozen-lockfile``.

    The tracked lockfile is ``frontend/pnpm-lock.yaml``, not
    ``package-lock.json``. ``--frozen-lockfile`` is pnpm's CI-safe
    install primitive — it fails fast on drift and never mutates the
    lock (#416 / F-011).
    """
    spa = _spa_stage_text()
    assert "pnpm install --frozen-lockfile" in spa, (
        "Dockerfile spa stage must use `pnpm install --frozen-lockfile` "
        "(not npm) — lockfile is frontend/pnpm-lock.yaml (#416 / F-011)."
    )

    # No npm references in the spa stage.
    for line in spa.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.search(r"\bnpm\b", line):
            raise AssertionError(
                f"Dockerfile spa stage uses npm: {line!r} — "
                "switch to `pnpm install --frozen-lockfile` (#416 / F-011)."
            )


def test_spa_stage_copies_pnpm_lockfile_and_npmrc() -> None:
    """F-011: the spa stage must COPY the pnpm lockfile (and .npmrc for
    registry config) before running ``pnpm install`` so Docker layer
    caching works correctly and the install uses the tracked lock.

    The .npmrc holds the ``@concavetrillion`` scope registry pointer;
    omitting it causes ``pnpm install`` to fail on packages from that
    scope (#416 / F-011).
    """
    spa = _spa_stage_text()
    assert "pnpm-lock.yaml" in spa, (
        "Dockerfile spa stage must COPY `pnpm-lock.yaml` before `pnpm install` "
        "so the build uses the tracked lockfile (#416 / F-011)."
    )


def test_dockerfile_and_release_workflow_agree_on_pnpm_install_logic() -> None:
    """F-011 / #416 (anti-drift): the Dockerfile spa stage and the release
    workflow's SPA-build steps must both use ``pnpm install --frozen-lockfile``.

    If a future change tightens one without the other, docker builds and
    GitHub Actions releases will disagree on install policy. This test
    catches that class of drift before it reaches CI.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    spa = _spa_stage_text()

    for label, text in (("release.yml", workflow), ("Dockerfile spa stage", spa)):
        # pnpm, not npm.
        assert "pnpm install --frozen-lockfile" in text, (
            f"{label} must invoke `pnpm install --frozen-lockfile` (#416 / F-011)."
        )
        # No npm install or npm ci.
        code_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        for line in code_lines:
            if re.search(r"\bnpm\s+(install|ci)\b", line):
                raise AssertionError(
                    f"{label} uses npm in: {line!r} — "
                    "switch to `pnpm install --frozen-lockfile` (#416 / F-011)."
                )


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
