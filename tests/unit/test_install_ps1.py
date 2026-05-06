"""Shape pins for the Windows PowerShell installer landed in iter 23.

Text-grep style — `install.ps1` is meant to run on a stranger's Windows
box via ``irm … | iex``, so we don't exec it here. We just enforce the
structural invariants that, if broken, would silently turn the
installer into a footgun.

Mirrors ``test_install_sh.py``: same load-bearing invariants
(strict-mode flag, python version preflight, ``uv tool install``,
``/releases/latest`` not ``/tags``, canonical entrypoint, repo slug)
but expressed in PowerShell idiom (``$ErrorActionPreference``,
``Invoke-RestMethod``, ``Test-Command``).

The peer ``pd-prep-for-pgdp/install.ps1`` is the structural model;
divergence is intentional in two places:

* B-27 parity: this script uses ``/releases/latest`` (the pgdp peer
  still uses ``/tags`` — peer flip is out of scope here).
* No CUDA/GPU branch: pd-ocr-labeler-spa has no GPU extras, so
  ``nvidia-smi`` detection is omitted (matches install.sh).

PowerShell 5.1 compatibility is the floor (the version Windows 10/11
ship with). We avoid pwsh-7-only features (e.g. ``??`` null-coalesce,
``ForEach-Object -Parallel``) so the script runs out-of-the-box on a
plain Windows install — same rationale as the pgdp peer.

We do NOT run ``pwsh -NoProfile -Command 'Get-Command -Syntax …'`` as
a syntax check because ``pwsh`` is unlikely to be on the devcontainer
PATH; if it ever is, that's a fine future tightening.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_PS1 = REPO_ROOT / "install.ps1"
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
MISE_TOML = REPO_ROOT / "mise.toml"


# ---------------------------------------------------------------------------
# Helpers — introspect from authoritative sources
# ---------------------------------------------------------------------------


def _entrypoint_name() -> str:
    """Read the canonical console-script name from pyproject.toml."""
    data = tomllib.loads(PYPROJECT_TOML.read_text())
    scripts = data["project"]["scripts"]
    assert len(scripts) == 1, f"expected exactly one [project.scripts] entry, got {list(scripts)}"
    return next(iter(scripts.keys()))


def _python_major_minor_from_mise() -> str:
    """Return the Python pin from mise.toml — e.g. '3.13'."""
    data = tomllib.loads(MISE_TOML.read_text())
    py = data["tools"]["python"]
    m = re.match(r"^(\d+\.\d+)", str(py))
    assert m, f"unexpected python pin in mise.toml: {py!r}"
    return m.group(1)


# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------


def test_install_ps1_exists_at_repo_root():
    assert INSTALL_PS1.is_file(), f"install.ps1 missing at {INSTALL_PS1}"


# ---------------------------------------------------------------------------
# Strictness — the PS analogue of `set -euo pipefail`
# ---------------------------------------------------------------------------


def test_install_ps1_sets_strict_error_action():
    # `$ErrorActionPreference = 'Stop'` is the PowerShell strict-mode
    # incantation — without it, non-terminating errors (most of them in
    # PowerShell) keep the pipeline going and turn a half-installed
    # state into a quiet UX papercut. Mirror install.sh's strict mode.
    text = INSTALL_PS1.read_text()
    # Accept either single or double quotes around 'Stop' so a future
    # quoting-style cleanup doesn't trip the test.
    assert re.search(r"\$ErrorActionPreference\s*=\s*[\"']Stop[\"']", text), (
        "install.ps1 must set `$ErrorActionPreference = 'Stop'` for fail-fast semantics"
    )


# ---------------------------------------------------------------------------
# Content invariants — sourced from authoritative manifests
# ---------------------------------------------------------------------------


def test_install_ps1_mentions_pinned_python_major():
    # If we bump Python in mise.toml, the installer's user-facing text
    # block needs to follow — otherwise users running the script see
    # stale prerequisite info. Same coupling as install.sh.
    py = _python_major_minor_from_mise()
    text = INSTALL_PS1.read_text()
    assert py in text, f"install.ps1 must reference the pinned Python {py} from mise.toml"


def test_install_ps1_runs_python_version_preflight():
    """install.ps1 must do a runtime python version check, not just a comment.

    Mirrors test_install_sh_runs_python_version_preflight (B-25
    behavioural pin): the script must actually invoke ``python -c
    'import sys ...'`` so a system Python that's too old surfaces a
    note up-front rather than the user finding out from a confusing
    ``uv tool install`` failure mode. Informational, not gating —
    ``uv tool install`` auto-downloads Python 3.13 when missing — but
    the behavioural step must exist.

    Note: Windows uses ``python``, not ``python3`` (the Microsoft Store
    Python alias and the typical installer both register ``python``),
    so we match ``python -c`` rather than ``python3 -c``.
    """
    text = INSTALL_PS1.read_text()
    assert re.search(r"\bpython\s+-c\b", text), (
        "install.ps1 must call `python -c ...` to inspect the system Python version"
    )
    assert "sys.version_info" in text, (
        "install.ps1's python preflight must inspect `sys.version_info` (not just print version)"
    )


def test_install_ps1_uses_uv_tool_install():
    # Peer-mirror with pd-prep-for-pgdp/install.ps1 and the local
    # install.sh. Switching to pip / pipx / poetry would break the
    # documented "no toolchain needed" promise (uv handles Python
    # download too).
    #
    # B-35: tighten beyond a bare substring to require the full
    # `uv tool install --reinstall <wheel-arg>` form. The bare
    # substring would have passed against a comment, a Write-Host
    # message, or a regression that drops `--reinstall` (and so
    # silently fails on the second `install.ps1` run because the
    # tool already exists). The wheel-file argument is also load-
    # bearing — without it `uv tool install` doesn't know what to
    # install.
    text = INSTALL_PS1.read_text()
    assert re.search(r"uv tool install\s+--reinstall\s+\S+", text), (
        "install.ps1 must call `uv tool install --reinstall <wheel>` "
        "(peer-mirror with pd-prep-for-pgdp/install.ps1; --reinstall "
        "makes re-runs idempotent, the wheel arg names what to install)"
    )


def test_install_ps1_names_canonical_entrypoint():
    # Sourced live from pyproject.toml's [project.scripts] so a rename
    # there can't leave the installer's success-message stale.
    entry = _entrypoint_name()
    text = INSTALL_PS1.read_text()
    assert entry in text, (
        f"install.ps1 must mention the canonical entrypoint {entry!r} from pyproject.toml [project.scripts]"
    )


def test_install_ps1_uses_releases_latest_endpoint():
    """install.ps1 must resolve "latest" via `/releases/latest`, not `/tags`.

    Mirrors test_install_sh_uses_releases_latest_endpoint (B-27). The
    `/tags` endpoint orders by commit-date of the tagged sha, which is
    wrong for two pre-1.0 quirks: re-tagged refs (this repo retagged
    v0.0 → v0.0.0 in iter 7) and hot-fix back-port flows tagged on a
    release branch. `/releases/latest` returns the most recent
    *published* release (ignoring drafts/prereleases) and embeds asset
    URLs directly — both more correct and saves a round-trip vs
    `/tags` + `/releases/tags/<tag>`.

    This is an intentional divergence from peer
    ``pd-prep-for-pgdp/install.ps1``, which still uses `/tags`.
    """
    text = INSTALL_PS1.read_text()
    assert "/releases/latest" in text, (
        "install.ps1 must use the GitHub `/releases/latest` endpoint to resolve the version"
    )
    # Belt-and-braces: forbid the legacy bare `/tags` listing (the
    # `/repos/X/tags` endpoint), which orders by commit-date and is
    # the original B-27 footgun. `/releases/tags/<tag>` (a different
    # endpoint that fetches a specific release by tag name) is fine
    # if some future iter needs it — that's why we match the *bare*
    # `/repos/<owner>/<name>/tags` shape only.
    assert not re.search(r"/repos/[^/\s\"']+/[^/\s\"']+/tags\b(?!/)", text), (
        "install.ps1 must not use the bare `/repos/X/tags` endpoint (use `/releases/latest` instead)"
    )


def test_install_ps1_references_correct_repo_slug():
    # If the GitHub repo is renamed or forked under a different org,
    # the installer points at the wrong releases. Pin to the homepage
    # URL declared in pyproject.toml so a single rename in
    # [project.urls] fails this test loudly. Same coupling as
    # install.sh.
    data = tomllib.loads(PYPROJECT_TOML.read_text())
    homepage = data["project"]["urls"]["Homepage"]
    m = re.match(r"^https://github\.com/([^/]+/[^/]+?)/?$", homepage)
    assert m, f"unexpected Homepage URL shape: {homepage!r}"
    slug = m.group(1)
    text = INSTALL_PS1.read_text()
    assert slug in text, (
        f"install.ps1 must reference the repo slug {slug!r} (from pyproject.toml [project.urls].Homepage)"
    )


# ---------------------------------------------------------------------------
# B-32 — Test-Command must use an explicit Boolean return
# ---------------------------------------------------------------------------


def test_test_command_returns_explicit_boolean() -> None:
    """B-32: ``Test-Command`` must return an explicit ``$true``/``$false``.

    The previous form piped ``Get-Command`` through ``ForEach-Object {
    return $true }`` and relied on PowerShell's pipeline coercion. The
    callers happened to work because ``-not @($true, $false)`` and
    ``-not $false`` both yield the right Boolean, but the function
    actually returned an array on the success path. Anyone refactoring
    the helper would inherit the footgun.

    The fix is the unambiguous ``return $null -ne (Get-Command ...)``
    one-liner. Pin both:
      * the helper uses ``$null -ne (...)`` (or equivalent ``[bool](...)``);
      * the helper does NOT use the ``ForEach-Object { return $true }``
        anti-pattern.
    """
    text = INSTALL_PS1.read_text()
    # Locate the function body — be generous about whitespace.
    body_match = re.search(
        r"function\s+Test-Command\b[^{]*\{(?P<body>.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert body_match, "install.ps1 must define a `Test-Command` function"
    body = body_match.group("body")
    # Must use an explicit-Boolean primitive. Either `$null -ne (...)`
    # or `[bool](...)` is acceptable; both yield exactly one Boolean.
    assert re.search(r"\$null\s+-ne\s+\(", body) or re.search(r"\[bool\]\s*\(", body), (
        "Test-Command must return an explicit Boolean via `$null -ne (...)` or `[bool](...)` (B-32). "
        f"Body was:\n{body}"
    )
    # Must NOT use the array-returning ForEach-Object anti-pattern.
    assert not re.search(r"ForEach-Object\s*\{\s*return\s+\$true\s*\}", body), (
        "Test-Command must not use `ForEach-Object { return $true }` — "
        "that emits an array on the success path (B-32). "
        f"Body was:\n{body}"
    )


# ---------------------------------------------------------------------------
# B-33 — MS Store stub Python redirector detection
# ---------------------------------------------------------------------------


def test_install_ps1_detects_ms_store_stub_python() -> None:
    """B-33: install.ps1 must detect the Microsoft Store stub redirector.

    On Windows 10/11 with no real Python installed, ``python.exe``
    resolves to ``%LocalAppData%\\Microsoft\\WindowsApps\\python.exe`` —
    a Store reparse-point stub that exits without running when given
    arguments. ``Test-Command "python"`` happily returns ``$true`` for
    it. The fix is to invoke ``python --version``, capture stdout/stderr,
    and check that it matches the real-Python output shape
    (``Python <maj>.<min>.<patch>``).

    Pin the regex so a regression to the previous shape ("just trust
    Test-Command") is caught.
    """
    text = INSTALL_PS1.read_text()
    # The script must invoke `python --version` (the stub-detection probe).
    assert re.search(r"\bpython\s+--version\b", text), (
        "install.ps1 must call `python --version` to probe for the MS Store stub (B-33)"
    )
    # The script must check for the real-Python output shape. We
    # accept any regex-shaped check that pins at least the
    # ``Python <digits>.<digits>`` prefix — the major.minor anchor is
    # what discriminates real Python (always prints the version) from
    # the Store stub (prints a "Python was not found" reparse message
    # that does not start with that shape). B-40 loosened from a
    # strict ``\d+\.\d+\.\d+`` end-anchored match (which rejected
    # pre-release Pythons like ``3.14.0a1``) to a leading-anchored
    # major.minor match; the regex literal in the script must contain
    # at least ``\d+\.\d+`` (with the optional ``(\.\d+)?`` patch
    # group acceptable). A bare ``Python `` substring with no digit
    # check would let the stub through.
    assert r"\d+\.\d+" in text, (
        r"install.ps1 must include a `\d+\.\d+` (or stricter) regex literal "
        "so the MS Store stub is detected (B-33/B-40). A version-shape check "
        "without digit groups would match the stub's error output too."
    )
    # Must also use `-notmatch` (the regex anti-pattern) against the
    # version-output variable — otherwise a regression that prints the
    # regex but never branches on it would slip through.
    assert "-notmatch" in text, "install.ps1 must use `-notmatch` to detect non-version output (B-33)"


# ---------------------------------------------------------------------------
# Length sanity — keep the chunk reviewable
# ---------------------------------------------------------------------------


def test_install_ps1_under_size_budget():
    # Keep the installer scannable in one screen. Soft-cap at 140 lines
    # to leave headroom for PowerShell's chattier idiom (Test-Command
    # helper, try/catch blocks, here-string error message, B-33 MS
    # Store stub detection branch) but still flag accidental sprawl.
    # install.sh sits at 95 with an 80-line target / 100 hard cap;
    # PowerShell needs a few more lines for the same logic, plus the
    # Windows-only stub-detection branch that has no install.sh peer.
    line_count = len(INSTALL_PS1.read_text().splitlines())
    assert line_count <= 140, (
        f"install.ps1 has grown to {line_count} lines; consider extracting "
        "logic to a helper script before the installer becomes hard to audit"
    )
