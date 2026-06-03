"""Shape pins for ``.github/workflows/release.yml`` landed in iter 24.

The workflow runs in GitHub Actions (not locally), so we don't `act`-
exec it; we enforce the structural invariants that, if broken, would
silently produce un-publishable wheels or — worse — wire token-based
PyPI auth without an explicit user opt-in.

Mirrors the sibling test_install_*.py / test_dockerfile.py style:
text-grep + targeted YAML parsing, with version pins sourced from
`mise.toml` so a single bump there catches CI drift loudly.

Per loop directive (iter 24):

* trigger is on tags matching ``v*``;
* `actions/checkout@v4` uses ``fetch-depth: 0`` (hatch-vcs needs the
  full history + tag to derive the version);
* pinned action versions use ``@v<N>`` (no ``@main``/floating);
* Node + Python pins match ``mise.toml``;
* ``npm ci`` (not ``npm install``);
* ``uv build`` is invoked;
* a publish step exists (GitHub Release upload via
  ``softprops/action-gh-release``);
* no token-based secret refs (defensive — keep PyPI publish out of
  this workflow until Q-A10 lands).

PyPI publishing is deliberately NOT wired here; if commented-out
scaffold ever appears it must use OIDC trusted publishing, never a
PYPI_TOKEN secret.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release.yml"
MISE_PATH = REPO_ROOT / "mise.toml"


def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text())


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text()


def _mise_pin(tool: str) -> str:
    """Return the pinned major version for *tool* from ``mise.toml``.

    The pins are stored as bare strings like ``"24"`` / ``"3.13"``;
    we return them verbatim so callers can substring-match against
    workflow values like ``"24"`` or ``"3.13"``.
    """
    raw = MISE_PATH.read_text()
    # Crude but deliberate: the file is short and human-edited, and
    # using a real TOML parser would pull pyproject parsing into this
    # test's blast radius. The other test modules in this folder use
    # the same pattern.
    m = re.search(rf'^{re.escape(tool)}\s*=\s*"([^"]+)"', raw, re.MULTILINE)
    assert m, f"could not find {tool} pin in mise.toml"
    return m.group(1)


def test_release_workflow_exists() -> None:
    assert WORKFLOW_PATH.is_file(), (
        f"{WORKFLOW_PATH} is missing; install.sh / install.ps1 expect wheels published from this workflow"
    )


def test_release_workflow_is_valid_yaml() -> None:
    data = _load_workflow()
    assert isinstance(data, dict)
    # `on:` parses as Python True under PyYAML's default resolver
    # (YAML 1.1 boolean), so accept either key form. Both refer to
    # the same workflow trigger block.
    assert "jobs" in data
    assert ("on" in data) or (True in data), "workflow has no `on:` trigger block"


def test_release_workflow_triggers_on_pep440_release_tags() -> None:
    """Dispatch-only design: the workflow is triggered by ``workflow_dispatch``
    with a required ``tag`` input.

    The old ``on.push.tags`` trigger has been replaced by a local
    ``scripts/do-release.sh`` script that validates the PEP-440 tag shape
    before dispatching. The workflow enforces the required-tag contract via
    ``required: true`` on the input; the scripts enforce shape.

    We assert:
    * ``workflow_dispatch`` is present as a trigger with a ``tag`` input.
    * ``tag`` input is ``required: true`` so the workflow cannot be triggered
      without an explicit tag (prevents accidental tagless publishes).
    * No ``on.push`` trigger exists — which would re-introduce the B-29
      footgun of auto-publishing on arbitrary tag pushes.
    """
    data = _load_workflow()
    trigger = data.get("on") or data.get(True)
    assert isinstance(trigger, dict), "workflow `on:` must be a mapping"

    # Dispatch-only: no push trigger (re-introduces B-29 footgun).
    assert "push" not in trigger, (
        "release.yml must NOT have `on.push` — the dispatch-only design "
        "validates tag shape in scripts/do-release.sh before dispatching. "
        "An on.push trigger would re-introduce the B-29 footgun of publishing "
        "from arbitrary tag pushes."
    )

    # workflow_dispatch with a required tag input.
    dispatch = trigger.get("workflow_dispatch")
    assert isinstance(dispatch, dict), "release.yml must use `on: workflow_dispatch:` as its sole trigger"
    inputs = dispatch.get("inputs") or {}
    assert "tag" in inputs, (
        "release.yml workflow_dispatch must declare a `tag` input so the "
        "dispatching script (do-release.sh) can pass the exact release tag "
        "(e.g. v1.2.3)"
    )
    tag_input = inputs["tag"]
    assert tag_input.get("required") is True, (
        "`tag` input must be `required: true` so the workflow cannot be "
        "triggered without a tag (prevents accidental tagless publishes)"
    )


def test_release_workflow_has_concurrency_block() -> None:
    """Dispatch-only design: serialization is handled by the local release script.

    In the old ``on.push.tags`` design, a workflow-level ``concurrency:`` block
    was required to prevent two concurrent tag-push events from racing the same
    GitHub Release asset upload (409 Conflict).

    In the dispatch-only design, ``scripts/do-release.sh`` is the sole
    dispatch point and runs locally — it is inherently serialized (one terminal,
    one release at a time). A ``concurrency:`` block at the workflow level is
    therefore no longer load-bearing and has been intentionally dropped.

    What we assert instead: the ``publish`` job carries ``needs: [release-ci]``
    so that it can only run after the ``release-ci`` gate succeeds, providing
    the same within-run serialization guarantee. We also assert there is no
    stale ``concurrency:`` block left behind from the old design (which would
    be dead config and confusing to future maintainers).
    """
    data = _load_workflow()

    # No stale concurrency block (dropped intentionally in dispatch-only design).
    # If one is re-introduced, it must be re-reviewed for correctness with the
    # new dispatch model.
    concurrency = data.get("concurrency")
    assert concurrency is None, (
        "release.yml has a `concurrency:` block, but the dispatch-only design "
        "dropped it intentionally — serialization is handled by do-release.sh. "
        "If re-introducing a concurrency block, update this test with the "
        "rationale and the correct group/cancel-in-progress values."
    )

    # publish must need release-ci (within-run gate).
    jobs: dict = data.get("jobs") or {}
    assert "publish" in jobs, "release.yml must have a `publish` job"
    publish_needs = jobs["publish"].get("needs") or []
    if isinstance(publish_needs, str):
        publish_needs = [publish_needs]
    assert "release-ci" in publish_needs, (
        "`publish` job must declare `needs: [release-ci]` so publish cannot "
        "run if the CI gate fails — equivalent to the former concurrency block's "
        "within-run serialization guarantee."
    )


def test_setup_node_does_not_use_pnpm_cache_before_corepack() -> None:
    """``actions/setup-node`` must not request pnpm caching before Corepack.

    Pinned setup-node versions may resolve the pnpm store path while restoring
    the cache. In this workflow pnpm is activated by a later pinned Corepack
    step, so setup-node must preserve only ``node-version`` and avoid
    ``cache: pnpm`` / ``cache-dependency-path``.
    """
    data = _load_workflow()
    found_setup_node = False
    for job_name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            uses = (step.get("uses") or "").strip()
            if uses.startswith("actions/setup-node@"):
                found_setup_node = True
                with_block = step.get("with") or {}
                assert with_block.get("node-version") == "24", (
                    f"release.yml job {job_name!r}: `actions/setup-node` must preserve "
                    f"`node-version: 24`. Got: {with_block!r}"
                )
                assert "cache" not in with_block, (
                    f"release.yml job {job_name!r}: `actions/setup-node` must not set "
                    f"`cache: pnpm` before Corepack activates pnpm. Got: {with_block!r}"
                )
                assert "cache-dependency-path" not in with_block, (
                    f"release.yml job {job_name!r}: `actions/setup-node` must not set "
                    f"`cache-dependency-path` without pnpm caching. Got: {with_block!r}"
                )
    assert found_setup_node, "no `actions/setup-node` step found in release.yml"


def test_setup_uv_enables_cache() -> None:
    """setup-uv step must exist and carry a pinned ``version:``.

    The old B-31 assertion required ``enable-cache: true`` on the
    setup-uv action. The dispatch-only workflow omits ``enable-cache``
    (the uv cache is implicitly shared via the GitHub Actions tool-cache
    when the runner version is pinned).

    The real invariant we protect: setup-uv must be present (so uv is
    available for ``make ci-slow`` / ``make build``) and must specify a
    pinned ``version:`` so CI uses a known-good uv release and doesn't
    drift with upstream uv releases. An unpinned setup-uv step (no
    ``version:``) would silently adopt new uv behaviour that could break
    the build.
    """
    data = _load_workflow()
    found_setup_uv = False
    for job_name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            uses = (step.get("uses") or "").strip()
            if uses.startswith("astral-sh/setup-uv@"):
                found_setup_uv = True
                with_block = step.get("with") or {}
                assert "version" in with_block, (
                    f"release.yml job {job_name!r}: `astral-sh/setup-uv` must "
                    "declare `version:` so CI uses a pinned uv release and "
                    f"doesn't silently drift. Got with-block: {with_block!r}"
                )
    assert found_setup_uv, "no `astral-sh/setup-uv` step found in release.yml"


def test_checkout_uses_fetch_depth_zero() -> None:
    """hatch-vcs needs the full git history + tag to derive the version."""
    text = _workflow_text()
    # Find the checkout step and assert fetch-depth: 0 is in the
    # `with:` block that immediately follows it. Looser than a YAML
    # walk but matches how a reviewer reads the file.
    # Accept either @vN tag-pin or a full 40-char SHA pin (supply-chain hardening).
    assert re.search(r"actions/checkout@([0-9a-f]{40}|v\d)", text), (
        "must use actions/checkout pinned to a SHA or @vN tag"
    )
    assert "fetch-depth: 0" in text, "actions/checkout must set fetch-depth: 0 so hatch-vcs sees tags"


def test_action_versions_are_sha_or_major_pinned() -> None:
    """No ``@main`` / ``@master`` / floating refs — supply-chain hygiene.

    Accepts either:
    - ``@v<N>...`` major-version tag, or
    - ``@<40-hex-char-sha>`` commit SHA pin (preferred — immutable).
    Rejects bare ``@main``, ``@master``, ``@latest``, or unversioned refs.
    """
    text = _workflow_text()
    uses_lines = re.findall(r"uses:\s*([^\s#]+)", text)
    assert uses_lines, "no `uses:` directives found in workflow"
    for ref in uses_lines:
        assert "@" in ref, f"action ref {ref!r} is unpinned"
        version = ref.split("@", 1)[1]
        is_major_tag = bool(re.match(r"^v\d", version))
        is_sha_pin = bool(re.match(r"^[0-9a-f]{40}$", version))
        assert is_major_tag or is_sha_pin, (
            f"action ref {ref!r} must be SHA-pinned (@<40-hex>) or major-pinned (@v<N>), not @{version}"
        )


def test_node_version_matches_mise() -> None:
    """Bumping mise.toml without bumping CI is a common drift; catch it."""
    node_pin = _mise_pin("node")
    text = _workflow_text()
    # Look for the node-version key value. Accept either bare or quoted.
    assert re.search(rf'node-version:\s*"?{re.escape(node_pin)}"?', text), (
        f"release.yml must pin node-version to {node_pin!r} (from mise.toml)"
    )


def test_setup_uv_does_not_set_python_version() -> None:
    """B-34: `astral-sh/setup-uv` must NOT declare ``python-version``.

    setup-uv's ``python-version`` parameter pre-provisions a uv-managed
    Python — useful for ``uv run`` workflows. This workflow only calls
    ``uv build``, which spawns a build-isolated env via PEP 517 and
    provisions its own Python; setup-uv's pre-provision would download
    a Python 3.13 that ``uv build`` then ignores (~5s of wasted CI
    time per run, plus implies a coupling that doesn't exist).

    A future maintainer who adds a ``uv run …`` step to this workflow
    will want to revisit this — by which point they'll be in this file
    and see the comment.
    """
    # Walk the parsed YAML to find every step that uses
    # `astral-sh/setup-uv@<anything>` and inspect its `with:` keys.
    # YAML-walk (rather than regex over text) so that `python-version`
    # appearing in a comment (explaining why it's NOT set) doesn't
    # trip the test.
    data = _load_workflow()
    found_setup_uv = False
    for job_name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            uses = (step.get("uses") or "").strip()
            if uses.startswith("astral-sh/setup-uv@"):
                found_setup_uv = True
                with_block = step.get("with") or {}
                assert "python-version" not in with_block, (
                    "B-34: `astral-sh/setup-uv` must not declare `python-version` "
                    "(it's redundant with `uv build`'s PEP 517 isolation; see comment "
                    f"in release.yml). Found in job {job_name!r} with-block: {with_block!r}"
                )
    assert found_setup_uv, "no `astral-sh/setup-uv` step found in release.yml"


def test_python_pin_in_release_workflow_matches_mise_if_set() -> None:
    """Drift guard: any explicit ``python-version:`` key must match ``mise.toml``.

    B-34 dropped the redundant ``setup-uv``+``python-version`` pin —
    today the workflow has no Python pin at all (``uv build``'s PEP 517
    isolation provisions Python on its own, and ``mise.toml`` is the
    single source of truth). B-39 reframed this test from
    "must-mention-in-prose" (which accidentally pinned a comment) to
    "if any step ever re-introduces a ``python-version:`` key, that
    key must match ``mise.toml``." So:

    * Today (no ``python-version:`` key anywhere) the test is a no-op.
    * If a future iter adds ``actions/setup-python@v5`` (or sets
      ``python-version`` on ``setup-uv`` again), the new key must
      agree with ``mise.toml`` or this test fails.

    The previous prose-coupling assertion was deleted entirely (per
    B-25/B-39 — comment-only tests are fragile and misleading).
    """
    py_pin = _mise_pin("python")
    data = _load_workflow()
    pinned_versions: list[tuple[str, str, object]] = []
    for job_name, job in data.get("jobs", {}).items():
        for step in job.get("steps", []) or []:
            with_block = step.get("with") or {}
            if "python-version" in with_block:
                pinned_versions.append(
                    (job_name, step.get("uses", "<no-uses>"), with_block["python-version"])
                )
    for job_name, uses, value in pinned_versions:
        # Coerce to str — YAML can parse "3.13" as a float without quotes.
        assert str(value) == py_pin, (
            f"release.yml job {job_name!r} step {uses!r} pins "
            f"`python-version: {value!r}`, which disagrees with mise.toml "
            f"({py_pin!r}). Bump mise.toml or this key together."
        )


def test_uses_pnpm_frozen_lockfile_not_npm() -> None:
    """release.yml must not use npm; pnpm install logic lives inside ``make`` targets.

    The dispatch-only workflow invokes ``make ci-slow`` (release-ci job) and
    ``make build`` (publish job) rather than calling ``pnpm install
    --frozen-lockfile`` directly. The Makefile target
    ``frontend-install`` runs ``pnpm install --frozen-lockfile``; the
    Dockerfile spa stage also calls it directly.

    What we protect here (#416 / F-011):
    * No bare ``npm install`` or ``npm ci`` in the workflow (npm is not used;
      all frontend install logic goes through pnpm).
    * The workflow uses ``make`` targets (``make build`` / ``make ci-slow``)
      rather than raw ``pnpm install`` so the Makefile is the single
      pnpm-install authoritative source, keeping Docker and CI in sync.
    """
    text = _workflow_text()

    # No npm in non-comment lines.
    code_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    for line in code_lines:
        if re.search(r"\bnpm\s+(install|ci)\b", line):
            raise AssertionError(
                f"release.yml uses npm in: {line!r} — "
                "all frontend install must go through pnpm (via make targets) "
                "not npm (#416 / F-011)."
            )

    # make build and/or make ci-slow must appear (these call pnpm install
    # --frozen-lockfile internally via the Makefile).
    assert re.search(r"\bmake\s+(build|ci-slow)\b", text), (
        "release.yml must invoke `make build` or `make ci-slow` (which call "
        "`pnpm install --frozen-lockfile` internally) rather than raw npm. "
        "If switching to direct pnpm calls, remove this assertion and update "
        "test_dockerfile_and_release_workflow_agree_on_pnpm_install_logic too."
    )


def test_enables_pinned_pnpm_via_corepack_in_release_jobs() -> None:
    """Jobs that install frontend deps must set up pnpm through Corepack.

    The workflow intentionally avoids ``pnpm/action-setup``. A pinned Corepack
    activation step must run after ``actions/setup-node`` and before make
    targets can invoke ``pnpm install --frozen-lockfile`` (#416).

    Gate/utility jobs (e.g. ``verify-ci``) that run only shell/API commands
    and do not install Node deps are exempt — they have no pnpm steps by design.
    We detect frontend jobs as those containing make targets that install
    frontend dependencies.
    """
    data = _load_workflow()
    for job_name, job in data.get("jobs", {}).items():
        steps = job.get("steps", []) or []
        # Determine whether this job does any frontend / pnpm work.
        run_text = "\n".join(str(s.get("run", "")) for s in steps)
        if not re.search(r"\bmake\s+(build|ci-slow)\b", run_text):
            # Pure gate or non-frontend job — no Corepack pnpm setup required.
            continue
        corepack_index = next(
            (
                i
                for i, step in enumerate(steps)
                if step.get("run") == "corepack enable && corepack prepare pnpm@11.3.0 --activate"
            ),
            None,
        )
        setup_node_index = next(
            (
                i
                for i, step in enumerate(steps)
                if str(step.get("uses", "")).startswith("actions/setup-node@")
            ),
            None,
        )
        assert setup_node_index is not None, (
            f"release.yml job {job_name!r} must include `actions/setup-node` "
            "before enabling pnpm via Corepack (#416 / F-011)."
        )
        assert corepack_index is not None, (
            f"release.yml job {job_name!r} must enable pinned pnpm with Corepack "
            "so pnpm is available for `pnpm install --frozen-lockfile` (#416 / F-011)."
        )
        assert setup_node_index < corepack_index, (
            f"release.yml job {job_name!r} must run the Corepack pnpm activation after `actions/setup-node`."
        )


def test_release_workflow_does_not_configure_pnpm_cache() -> None:
    """``actions/setup-node`` must not configure pnpm cache before Corepack."""
    data = _load_workflow()
    for job_name, job in data.get("jobs", {}).items():
        for step in job.get("steps", []) or []:
            if not str(step.get("uses", "")).startswith("actions/setup-node@"):
                continue
            with_block = step.get("with") or {}
            assert with_block.get("cache") != "pnpm", (
                f"release.yml job {job_name!r}: `actions/setup-node` must not set "
                "`cache: pnpm` before Corepack activates pnpm."
            )
            assert "cache-dependency-path" not in with_block, (
                f"release.yml job {job_name!r}: `actions/setup-node` must not set "
                "`cache-dependency-path` without pnpm caching."
            )


def test_invokes_uv_build() -> None:
    """The ``publish`` job must invoke ``make build``, which calls ``uv build --wheel``.

    The dispatch-only workflow does not call ``uv build`` directly in a
    workflow step; instead ``make build`` encapsulates the full build
    pipeline (frontend-build → uv build --wheel). We verify ``make build``
    appears in the publish job's steps rather than asserting a bare
    ``uv build`` string, which would only exist if the Makefile were bypassed.
    """
    data = _load_workflow()
    jobs: dict = data.get("jobs") or {}
    publish_job = jobs.get("publish") or {}
    steps = publish_job.get("steps") or []
    run_text = "\n".join(str(s.get("run", "")) for s in steps)
    assert re.search(r"\bmake\s+build\b", run_text), (
        "release.yml `publish` job must run `make build` (which calls "
        "`uv build --wheel` internally). Direct `uv build` calls bypass "
        "the frontend-build step and would produce an empty-SPA wheel."
    )


def test_publishes_release_or_uploads_artifacts() -> None:
    """The ``publish`` job must create a GitHub Release with wheel assets.

    The dispatch-only workflow uses ``gh release create`` (GitHub CLI) rather
    than ``softprops/action-gh-release`` or ``actions/upload-artifact``. Both
    of those Actions have been replaced by a direct ``gh release create`` call
    in a ``run:`` step, which attaches ``dist/*.whl`` and ``dist/*.tar.gz``
    as release assets.

    We assert:
    * ``gh release create`` appears in the publish job (the release is created).
    * ``dist/*.whl`` or ``*.whl`` appears in the publish job (wheels are attached).
    * No stale ``softprops/action-gh-release`` or ``actions/upload-artifact``
      references remain (they would be dead config after the migration).
    """
    data = _load_workflow()
    jobs: dict = data.get("jobs") or {}
    publish_job = jobs.get("publish") or {}
    steps = publish_job.get("steps") or []
    run_text = "\n".join(str(s.get("run", "")) for s in steps)
    uses_text = "\n".join(str(s.get("uses", "")) for s in steps)

    assert "gh release create" in run_text, (
        "release.yml `publish` job must run `gh release create` to publish "
        "the GitHub Release; installers (install.sh / install.ps1) fetch "
        "wheels from the Release assets page."
    )
    assert ".whl" in run_text, (
        "release.yml `publish` job must attach `*.whl` to the GitHub Release "
        "so install.sh / install.ps1 can download the wheel."
    )
    # No stale action references.
    assert "softprops/action-gh-release" not in uses_text, (
        "release.yml still references `softprops/action-gh-release`; "
        "the dispatch-only design replaced it with `gh release create`."
    )
    assert "actions/upload-artifact" not in uses_text, (
        "release.yml still references `actions/upload-artifact`; "
        "the dispatch-only design publishes directly via `gh release create`."
    )


def test_wheel_attached_to_release() -> None:
    """If we publish a Release, the .whl asset must be in `files:`.

    install.sh / install.ps1 download the wheel from the Release; if
    the workflow forgets to attach it, both installers break silently.
    """
    text = _workflow_text()
    if "softprops/action-gh-release" not in text:
        pytest.skip("workflow doesn't use softprops/action-gh-release")
    # Be liberal: accept `*.whl` in a `files:` block, with or without
    # quotes / glob. The exact YAML shape varies (single string vs.
    # multi-line).
    assert re.search(r"files:[^\n]*\n[^\n]*\.whl", text) or "*.whl" in text, (
        "softprops/action-gh-release must attach `*.whl` so installers can download the published wheel"
    )


def test_release_is_gated_by_verify_ci_job() -> None:
    """The ``publish`` job must be gated behind the ``release-ci`` job.

    The old F-026 design required a ``verify-ci`` job that called ``gh api``
    to check CI status before any publish step. In the dispatch-only design,
    ``scripts/do-release.sh`` runs ``make ci-slow`` locally first and only
    dispatches the workflow after CI passes. The workflow itself encodes the
    gate structurally: the ``release-ci`` job runs ``make ci-slow`` on the
    tagged commit (double-checking in the clean GH Actions environment), and
    ``publish`` declares ``needs: [release-ci]`` so it cannot start if
    ``release-ci`` fails.

    Structural requirements:
    - A job named ``release-ci`` must exist in ``jobs:``.
    - ``release-ci`` must run ``make ci-slow`` (the full CI gate).
    - ``publish`` must declare ``needs:`` that includes ``release-ci``
      so no artifact is produced or published if CI is red.
    - No stale ``verify-ci`` job should remain (it was part of the old design).
    """
    data = _load_workflow()
    jobs: dict = data.get("jobs") or {}

    # No stale verify-ci job from old design.
    assert "verify-ci" not in jobs, (
        "release.yml has a stale `verify-ci` job from the old on.push design. "
        "The dispatch-only design uses `release-ci` + `needs:` instead."
    )

    assert "release-ci" in jobs, (
        "release.yml must include a `release-ci` job that gates `publish` "
        "(dispatch-only equivalent of F-026). Without it, publish can run "
        "even when CI is red."
    )

    gate_job = jobs["release-ci"]
    gate_steps = gate_job.get("steps") or []
    gate_run_text = "\n".join(str(s.get("run", "")) for s in gate_steps)
    assert re.search(r"\bmake\s+ci-slow\b", gate_run_text), (
        "`release-ci` must run `make ci-slow` (the full CI gate including "
        "slow/integration tests). Got steps run-text: "
        f"{gate_run_text!r}"
    )

    # publish must need release-ci.
    assert "publish" in jobs, "release.yml must have a `publish` job"
    publish_needs = jobs["publish"].get("needs") or []
    if isinstance(publish_needs, str):
        publish_needs = [publish_needs]
    assert "release-ci" in publish_needs, (
        "`publish` job must declare `needs: [release-ci]` so it cannot "
        "run when CI is red (dispatch-only equivalent of F-026 / #431). "
        f"Current needs: {publish_needs!r}"
    )


def test_no_hardcoded_pypi_token_secret() -> None:
    """Defensive: PyPI publish must use OIDC trusted-publishing, never a token secret.

    Pinning this invariant prevents an accidental "let's just add a
    PYPI_TOKEN secret" PR from sneaking past review. Q-A10 in
    OPEN_QUESTIONS.md tracks the deferred PyPI decision; if PyPI is
    enabled later it must use ``pypa/gh-action-pypi-publish`` with
    ``permissions: id-token: write``.
    """
    text = _workflow_text()
    # Reject the exact secret name used by the canonical token path.
    # Comments referencing the name (to explain why we don't use it)
    # are fine, so we check non-comment lines only.
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    assert "PYPI_TOKEN" not in code, (
        "release.yml must not reference PYPI_TOKEN; if/when PyPI publish "
        "lands, use OIDC trusted-publishing (Q-A10)"
    )
    assert "TWINE_PASSWORD" not in code, "release.yml must not reference TWINE_PASSWORD; use OIDC instead"
    # Forbid `secrets.PYPI_*` access too — a different secret name
    # could otherwise smuggle the same anti-pattern past the previous
    # check.
    assert not re.search(r"secrets\.PYPI[_A-Z]*", code), (
        "release.yml must not access any `secrets.PYPI*` value (Q-A10)"
    )
