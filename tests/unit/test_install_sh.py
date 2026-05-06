"""Shape pins for the end-user installer landed in iter 19.

Text-grep style — `install.sh` is meant to run on a stranger's machine
with `curl | bash`, so we don't exec it here; we just enforce the
structural invariants that, if broken, would silently turn the
installer into a footgun.

Mirrors the pd-prep-for-pgdp installer pattern (uv tool install +
GitHub release wheel download); see ``pd-prep-for-pgdp/install.sh``.
The directive in the iter-19 prompt mentioned ``pipx`` as a generic
fallback path, but since the canonical peer installer exists and is
what the user-facing docs already reference (``DEVELOPMENT.md``), we
mirror it instead — that keeps a single mental model across the
seven pd-* projects.

Load-bearing invariants (each has a regression here):

* File exists at the repo root and is executable. ``curl | bash``
  doesn't actually need the +x bit, but local clones using
  ``./install.sh`` do, and missing it is a quiet UX papercut.
* Bash shebang + ``set -euo pipefail`` so a partial install fails
  loudly instead of half-finishing.
* Names the canonical ``[project.scripts]`` entrypoint
  (``pd-ocr-labeler-ui``) so users know what to type next. Sourced
  live from ``pyproject.toml``, so a script-rename can't drift.
* References Python's pinned major from ``mise.toml`` (3.13) so a
  future Python bump fails this test before it ships a confusing
  installer.
* Uses ``uv tool install`` (not pipx, not pip) — peer-mirror
  ``pd-prep-for-pgdp/install.sh``.
* ``bash -n`` syntax check passes when bash is on PATH.

Install of ``install.ps1`` (Windows) and ``release.yml`` (GitHub
Actions) is deferred to subsequent iterations; this test pins the
sh-only chunk.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
MISE_TOML = REPO_ROOT / "mise.toml"


# ---------------------------------------------------------------------------
# Helpers — introspect from authoritative sources
# ---------------------------------------------------------------------------


def _entrypoint_name() -> str:
    """Read the canonical console-script name from pyproject.toml."""
    data = tomllib.loads(PYPROJECT_TOML.read_text())
    scripts = data["project"]["scripts"]
    # We rely on there being exactly one script in M0; if that ever
    # changes the test should be revisited rather than silently picking
    # the first key.
    assert len(scripts) == 1, f"expected exactly one [project.scripts] entry, got {list(scripts)}"
    return next(iter(scripts.keys()))


def _python_major_minor_from_mise() -> str:
    """Return the Python pin from mise.toml — e.g. '3.13'."""
    data = tomllib.loads(MISE_TOML.read_text())
    py = data["tools"]["python"]
    # mise allows full versions, but we pin to "3.13" — assert the
    # major.minor shape so a stricter pin (e.g. "3.13.2") still parses.
    m = re.match(r"^(\d+\.\d+)", str(py))
    assert m, f"unexpected python pin in mise.toml: {py!r}"
    return m.group(1)


# ---------------------------------------------------------------------------
# Existence + executable bit
# ---------------------------------------------------------------------------


def test_install_sh_exists_at_repo_root():
    assert INSTALL_SH.is_file(), f"install.sh missing at {INSTALL_SH}"


def test_install_sh_is_executable():
    # `curl | bash` doesn't need +x, but a local clone running
    # `./install.sh` does. Cheap and obvious failure mode to guard.
    assert os.access(INSTALL_SH, os.X_OK), "install.sh must be executable (chmod +x install.sh)"


# ---------------------------------------------------------------------------
# Shebang + strictness
# ---------------------------------------------------------------------------


def test_install_sh_uses_bash_shebang():
    first_line = INSTALL_SH.read_text().splitlines()[0]
    assert first_line == "#!/usr/bin/env bash", f"expected '#!/usr/bin/env bash' shebang, got {first_line!r}"


def test_install_sh_sets_strict_mode():
    # `set -euo pipefail` is the standard bash strict-mode incantation —
    # any of the three flags missing turns silent failures into bug
    # reports, so we pin all three together.
    text = INSTALL_SH.read_text()
    assert "set -euo pipefail" in text, "install.sh must `set -euo pipefail` for fail-fast semantics"


# ---------------------------------------------------------------------------
# Content invariants — sourced from authoritative manifests
# ---------------------------------------------------------------------------


def test_install_sh_mentions_pinned_python_major():
    # If we bump Python in mise.toml, the installer's user-facing
    # comment block needs to follow — otherwise users running the
    # script see stale prerequisite info.
    py = _python_major_minor_from_mise()
    text = INSTALL_SH.read_text()
    assert py in text, f"install.sh must reference the pinned Python {py} from mise.toml"


def test_install_sh_uses_uv_tool_install():
    # Peer-mirror with pd-prep-for-pgdp/install.sh. Switching to pip /
    # pipx / poetry would break the documented "no toolchain needed"
    # promise (uv handles Python download too).
    text = INSTALL_SH.read_text()
    assert "uv tool install" in text, (
        "install.sh must use `uv tool install` (peer-mirror with pd-prep-for-pgdp/install.sh)"
    )


def test_install_sh_names_canonical_entrypoint():
    # Sourced live from pyproject.toml's [project.scripts] so a rename
    # there can't leave the installer's success-message stale.
    entry = _entrypoint_name()
    text = INSTALL_SH.read_text()
    assert entry in text, (
        f"install.sh must mention the canonical entrypoint {entry!r} from pyproject.toml [project.scripts]"
    )


def test_install_sh_references_correct_repo_slug():
    # If the GitHub repo is renamed or forked under a different org,
    # the installer points at the wrong releases. Pin to the homepage
    # URL declared in pyproject.toml so a single rename in
    # [project.urls] fails this test loudly.
    data = tomllib.loads(PYPROJECT_TOML.read_text())
    homepage = data["project"]["urls"]["Homepage"]
    # Homepage is e.g. https://github.com/ConcaveTrillion/pd-ocr-labeler-spa
    m = re.match(r"^https://github\.com/([^/]+/[^/]+?)/?$", homepage)
    assert m, f"unexpected Homepage URL shape: {homepage!r}"
    slug = m.group(1)
    text = INSTALL_SH.read_text()
    assert slug in text, (
        f"install.sh must reference the repo slug {slug!r} (from pyproject.toml [project.urls].Homepage)"
    )


# ---------------------------------------------------------------------------
# Bash syntax check (skip-friendly — devcontainer has bash, but be safe)
# ---------------------------------------------------------------------------


def test_install_sh_bash_syntax_check():
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover — devcontainer has bash
        import pytest

        pytest.skip("bash not on PATH — cannot run `bash -n` syntax check")
    result = subprocess.run(
        [bash, "-n", str(INSTALL_SH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"install.sh failed `bash -n` syntax check:\n{result.stderr}"


# ---------------------------------------------------------------------------
# Length sanity — keep the chunk reviewable
# ---------------------------------------------------------------------------


def test_install_sh_under_size_budget():
    # The iter-19 directive caps install.sh at ~80 lines so reviewers
    # can scan it in one screen. Soft-cap at 100 to leave headroom for
    # a trailing comment block but still flag accidental sprawl.
    line_count = len(INSTALL_SH.read_text().splitlines())
    assert line_count <= 100, (
        f"install.sh has grown to {line_count} lines; consider extracting "
        "logic to a helper script before the installer becomes hard to audit"
    )
