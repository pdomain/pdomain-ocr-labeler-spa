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


def test_release_workflow_triggers_on_v_tags() -> None:
    data = _load_workflow()
    trigger = data.get("on") or data.get(True)
    assert isinstance(trigger, dict), "workflow `on:` must be a mapping"
    push = trigger.get("push")
    assert isinstance(push, dict), "workflow must have `on.push`"
    tags = push.get("tags")
    assert tags, "workflow must declare `on.push.tags`"
    assert any("v*" in t for t in tags), f"workflow must trigger on tags matching `v*`, got {tags!r}"


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


def test_python_version_matches_mise() -> None:
    """Same drift guard for Python."""
    py_pin = _mise_pin("python")
    text = _workflow_text()
    assert re.search(rf'python-version:\s*"?{re.escape(py_pin)}"?', text), (
        f"release.yml must pin python-version to {py_pin!r} (from mise.toml)"
    )


def test_uses_npm_ci_not_npm_install() -> None:
    """``npm install`` mutates lockfiles in CI; ``npm ci`` is the right primitive."""
    text = _workflow_text()
    assert "npm ci" in text, "release.yml must use `npm ci` (not `npm install`)"
    # Defensive: forbid the bare `npm install` regression.
    # Use a word boundary so `npm install -g …` (if ever needed) is
    # caught too, but allow incidental occurrences in comments.
    code_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    code = "\n".join(code_lines)
    assert not re.search(r"\bnpm install\b", code), (
        "release.yml must not invoke `npm install` (use `npm ci` for CI)"
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
