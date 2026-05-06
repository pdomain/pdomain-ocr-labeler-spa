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
    """B-29: tag triggers must be PEP-440-shaped, not the loose ``v*``.

    The previous ``v*`` glob would fire on `vfeature-test`, `vbeta`,
    `v0.0` (the deprecated retag-target removed in B-09), etc., any
    of which would publish a junk Release that `install.sh`'s
    `/releases/latest` endpoint would then surface to end users.

    We require:
      * `v[0-9]+.[0-9]+.[0-9]+`         — `v1.2.3` release shape, AND
      * `v[0-9]+.[0-9]+.[0-9]+-*`       — `v1.2.3-rc1` / `-beta` etc.

    Both glob forms must be present; nothing wider (e.g. `v*`,
    `v[0-9]*`) is allowed because each widening re-introduces the
    original footgun.
    """
    data = _load_workflow()
    trigger = data.get("on") or data.get(True)
    assert isinstance(trigger, dict), "workflow `on:` must be a mapping"
    push = trigger.get("push")
    assert isinstance(push, dict), "workflow must have `on.push`"
    tags = push.get("tags")
    assert tags, "workflow must declare `on.push.tags`"
    assert isinstance(tags, list), f"`on.push.tags` must be a list, got {type(tags).__name__}"

    # The strict release-shape glob must be present.
    release_glob = "v[0-9]+.[0-9]+.[0-9]+"
    prerelease_glob = "v[0-9]+.[0-9]+.[0-9]+-*"
    assert release_glob in tags, (
        f"workflow must trigger on PEP-440 release tags ({release_glob!r}); got {tags!r}"
    )
    assert prerelease_glob in tags, (
        f"workflow must also accept pre-release tags ({prerelease_glob!r}) "
        f"so `v1.2.3-rc1` triggers; got {tags!r}"
    )

    # Forbid the loose `v*` (and the equally-loose `v[0-9]*` cousin)
    # so a future widening can't silently re-introduce the B-29
    # footgun.
    forbidden = {"v*", "v[0-9]*", "v?*"}
    assert not (set(tags) & forbidden), (
        f"workflow tag glob must not include any of {forbidden} "
        f"(would re-introduce B-29 — `vfeature-test` etc. would publish); got {tags!r}"
    )


def test_release_workflow_has_concurrency_block() -> None:
    """B-30: concurrent tag-pushes (or a "Re-run all jobs" mid-publish)
    must serialize so two parallel publish runs don't race the same
    Release-asset upload (which surfaces as `409 Conflict` from
    softprops/action-gh-release).

    Pin both:
      * the `concurrency:` block exists at workflow scope; and
      * `cancel-in-progress: false` — release jobs are not safely
        cancellable mid-upload, so we queue the second run rather
        than abort the first.
    """
    data = _load_workflow()
    concurrency = data.get("concurrency")
    assert isinstance(concurrency, dict), (
        "release.yml must declare a workflow-level `concurrency:` block (B-30) "
        "to serialize per-tag publish runs"
    )
    group = concurrency.get("group")
    assert group and "${{ github.ref }}" in str(group), (
        f"`concurrency.group` must be keyed on `${{{{ github.ref }}}}` so "
        f"different tags don't block each other; got {group!r}"
    )
    # `cancel-in-progress` must be explicitly false. Default behaviour
    # for missing field is `false` too, but pinning the explicit value
    # makes the intent reviewable.
    cancel = concurrency.get("cancel-in-progress")
    assert cancel is False, (
        f"`concurrency.cancel-in-progress` must be `false` (release jobs "
        f"can't safely be cancelled mid-upload); got {cancel!r}"
    )


def test_setup_node_npm_cache_disabled_until_lockfile_lands() -> None:
    """B-37: until Q-A8 unblocks Node in the devcontainer and a real
    `frontend/package-lock.json` is committed, `actions/setup-node@v4`
    must NOT declare `cache: "npm"`.

    setup-node's npm-cache integration treats a missing lockfile at
    `cache-dependency-path` as a hard error ("Dependencies lock file
    is not found in …"), failing the workflow at the Setup Node.js
    step BEFORE the iter-26 two-pass install gets a chance to
    bootstrap the lockfile. Enabling the cache here would silently
    re-open B-28.

    YAML-walk the setup-node `with:` block (rather than regex over
    text) so the explanatory comment that names the parameter doesn't
    falsely trip this assertion. When Q-A8 lands the real lockfile,
    flip this test to assert `cache: "npm"` IS set (and re-introduce
    the `cache-dependency-path: frontend/package-lock.json` pin).

    The uv cache (`astral-sh/setup-uv` `enable-cache: true`) is the
    valid caching path today — `uv.lock` exists and the cache primes
    without a setup-step hard-fail. See
    `test_setup_uv_enables_cache`.
    """
    data = _load_workflow()
    found_setup_node = False
    for job_name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            uses = (step.get("uses") or "").strip()
            if uses.startswith("actions/setup-node@"):
                found_setup_node = True
                with_block = step.get("with") or {}
                assert "cache" not in with_block, (
                    "B-37: `actions/setup-node` must NOT declare a `cache:` key "
                    "until Q-A8 unblocks a committed `frontend/package-lock.json`. "
                    "setup-node hard-fails on missing lockfile when `cache:` is set, "
                    "which would re-open B-28. Found in job "
                    f"{job_name!r} with-block: {with_block!r}"
                )
                assert "cache-dependency-path" not in with_block, (
                    "B-37: drop `cache-dependency-path` together with `cache:` — "
                    "neither is meaningful without the other. Found in job "
                    f"{job_name!r} with-block: {with_block!r}"
                )
    assert found_setup_node, "no `actions/setup-node` step found in release.yml"


def test_setup_uv_enables_cache() -> None:
    """B-31: `astral-sh/setup-uv` must opt into `enable-cache: true`
    so `~/.cache/uv` is restored between CI runs (saves the
    build-isolated-env resolution cost on every `uv build`).
    """
    text = _workflow_text()
    assert re.search(r"enable-cache:\s*true", text), (
        "setup-uv must declare `enable-cache: true` for B-31 caching"
    )


def test_checkout_uses_fetch_depth_zero() -> None:
    """hatch-vcs needs the full git history + tag to derive the version."""
    text = _workflow_text()
    # Find the checkout step and assert fetch-depth: 0 is in the
    # `with:` block that immediately follows it. Looser than a YAML
    # walk but matches how a reviewer reads the file.
    assert "actions/checkout@v4" in text, "must use actions/checkout@v4"
    assert "fetch-depth: 0" in text, "actions/checkout must set fetch-depth: 0 so hatch-vcs sees tags"


def test_action_versions_are_major_pinned() -> None:
    """No ``@main`` / ``@master`` / floating refs — supply-chain hygiene."""
    text = _workflow_text()
    # Every `uses:` line should pin a `@v<N>` major or a sha. We
    # don't ship sha pins here, so enforce `@v<digit>` form.
    uses_lines = re.findall(r"uses:\s*([^\s]+)", text)
    assert uses_lines, "no `uses:` directives found in workflow"
    for ref in uses_lines:
        # Allow `owner/repo@v<N>...` form. Reject @main, @master,
        # @latest, or unversioned refs.
        assert "@" in ref, f"action ref {ref!r} is unpinned"
        version = ref.split("@", 1)[1]
        assert re.match(r"^v\d", version), f"action ref {ref!r} must be major-pinned (@v<N>), not @{version}"


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


def test_uses_npm_ci_not_npm_install() -> None:
    """``npm install`` mutates lockfiles in CI; ``npm ci`` is the right primitive.

    Exception (B-28): until Q-A8 unblocks Node in the devcontainer and
    a real `frontend/package-lock.json` is committed, the workflow uses
    a two-pass install — `npm install --package-lock-only` to bootstrap
    a lock when missing, then `npm ci` as the source of truth. The
    `--package-lock-only` invocation never touches `node_modules/` and
    cannot drift transitive versions inside CI, so the reproducibility
    concern that motivated this test is preserved.
    """
    text = _workflow_text()
    assert "npm ci" in text, "release.yml must use `npm ci` (not `npm install`)"
    # Defensive: forbid the bare `npm install` regression — a plain
    # `npm install` (no flags) on a non-comment line would re-introduce
    # the lockfile-mutation hazard. The bootstrap form
    # (`npm install --package-lock-only [...]`) is allowed.
    code_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    code = "\n".join(code_lines)
    # Match `npm install` only when NOT immediately followed by
    # `--package-lock-only` somewhere on the same line.
    for line in code.splitlines():
        if re.search(r"\bnpm install\b", line) and "--package-lock-only" not in line:
            raise AssertionError(
                f"release.yml line uses bare `npm install`: {line!r} — "
                "use `npm ci` (or `npm install --package-lock-only` to "
                "bootstrap a missing lockfile)."
            )


def test_uses_two_pass_install_with_lockfile_fallback() -> None:
    """B-28: the SPA-build step must handle both lockfile-present and
    lockfile-absent states.

    With a real `frontend/package-lock.json`, the bootstrap branch is a
    fast no-op and `npm ci` runs from the lock. Without it (Q-A8 still
    blocking), the bootstrap generates the lock in-place via
    `npm install --package-lock-only`, then `npm ci` consumes it. Both
    paths converge on a deterministic install.

    Pin the bootstrap form explicitly so a regression that drops it
    (and re-introduces the iter-24 first-tag-push failure) fails fast.

    B-41 BREADCRUMB — PLANNED OBSOLESCENCE
    --------------------------------------
    When Q-A8 unblocks (Node toolchain in devcontainer) and a real
    `frontend/package-lock.json` is committed, the bootstrap branch
    becomes permanent dead code. At that point: drop the
    `if [ ! -f package-lock.json ]; then npm install --package-lock-only ...; fi`
    block from BOTH `release.yml` AND `Dockerfile` (spa stage) in the
    SAME commit AND delete this assertion plus the cross-file pin in
    `tests/unit/test_dockerfile.py::test_dockerfile_and_release_workflow_agree_on_npm_install_logic`.
    All three changes must land together — splitting risks the
    iter-25 inconsistency this test was designed to prevent.
    """
    text = _workflow_text()
    assert "--package-lock-only" in text, (
        "release.yml must include the `npm install --package-lock-only` "
        "fallback so the workflow does not fail on the first tag push "
        "while `frontend/package-lock.json` is still absent (B-28 / Q-A8)."
    )
    # The fallback should be conditional — guarded by a `! -f
    # package-lock.json` shell test — so once a real lockfile lands the
    # bootstrap is a no-op rather than a mutation each run.
    assert re.search(r"!\s*-f\s+package-lock\.json", text), (
        "release.yml must guard the `--package-lock-only` bootstrap on "
        "`! -f package-lock.json` so it becomes a no-op once the real "
        "lockfile is committed."
    )


def test_invokes_uv_build() -> None:
    text = _workflow_text()
    assert "uv build" in text, "release.yml must invoke `uv build`"


def test_publishes_release_or_uploads_artifacts() -> None:
    """Either creates a GitHub Release with assets, or uploads artifacts."""
    text = _workflow_text()
    publishes = "softprops/action-gh-release" in text
    uploads = "actions/upload-artifact" in text
    assert publishes or uploads, (
        "release.yml must either publish a GitHub Release "
        "(softprops/action-gh-release) or upload artifacts "
        "(actions/upload-artifact); installers can't fetch wheels otherwise"
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
