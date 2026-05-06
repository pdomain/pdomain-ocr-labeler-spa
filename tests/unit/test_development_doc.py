"""``docs/DEVELOPMENT.md`` smoke shape.

Catches the most common drift modes between the development guide and
the actual Makefile / `mise.toml`:

* References a target that doesn't exist in the Makefile (e.g.
  someone renames ``frontend-install`` → ``ui-install`` and forgets to
  update the doc).
* References a Node/Python version pin that doesn't match
  ``mise.toml`` (so contributors install the wrong toolchain).

Pinning the doc here is cheap and keeps it honest. Doesn't replace
human review of clarity, but does force at least basic accuracy.
"""

from __future__ import annotations

import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "DEVELOPMENT.md"
MAKEFILE = Path(__file__).resolve().parents[2] / "Makefile"
MISE = Path(__file__).resolve().parents[2] / "mise.toml"


def test_development_doc_exists() -> None:
    assert DOC.is_file(), f"{DOC} missing"


def test_development_doc_references_only_existing_make_targets() -> None:
    """Every ``make <foo>`` invocation in the doc must resolve to a
    real Makefile target."""
    body = DOC.read_text()
    referenced = set(re.findall(r"make ([a-z][a-z0-9-]*)", body))

    mk = MAKEFILE.read_text()
    targets = set(re.findall(r"^([a-z][a-z0-9_-]*):", mk, re.MULTILINE))

    missing = referenced - targets
    assert not missing, f"DEVELOPMENT.md references make targets that don't exist: {missing}"


def test_development_doc_pins_match_mise_toml() -> None:
    """If the doc names Node/Python versions, they must match
    ``mise.toml`` so contributors don't install the wrong toolchain."""
    doc_text = DOC.read_text()
    mise_text = MISE.read_text()

    # Pull `node = "X"` and `python = "Y"` out of mise.toml.
    node_pin = re.search(r'^node\s*=\s*"([^"]+)"', mise_text, re.MULTILINE)
    python_pin = re.search(r'^python\s*=\s*"([^"]+)"', mise_text, re.MULTILINE)
    assert node_pin and python_pin, "mise.toml missing node/python pin"

    # The doc should mention both pins verbatim if it mentions versions
    # at all. We assert presence, not exclusion of others.
    assert f"Node {node_pin.group(1)}" in doc_text or f'node = "{node_pin.group(1)}"' in doc_text, (
        f"DEVELOPMENT.md drifts from mise.toml node pin {node_pin.group(1)!r}"
    )
    assert f"Python {python_pin.group(1)}" in doc_text or f'python = "{python_pin.group(1)}"' in doc_text, (
        f"DEVELOPMENT.md drifts from mise.toml python pin {python_pin.group(1)!r}"
    )


def test_development_doc_mentions_uv_install_path() -> None:
    """The ``uv`` install snippet (Astral's curl-based installer) is
    the canonical recovery path when a contributor doesn't have ``uv``
    on PATH outside the devcontainer. The mise.toml comment points at
    it; the dev doc should too."""
    body = DOC.read_text()
    assert "astral.sh/uv/install.sh" in body, (
        "DEVELOPMENT.md should reference the Astral uv installer for out-of-devcontainer setup"
    )


def test_development_doc_is_honest_about_m0_limits() -> None:
    """B-12 regression: the dev-server section used to claim
    ``make dev`` proxies ``/`` to Vite and a contributor could open
    ``http://localhost:5173`` to see "the SPA" — both halves are false
    in M0 (``GET /`` is 404 on the backend; the Vite scaffold has no
    real SPA). Pin the doc to *call out* the M0 status so a first-
    time contributor doesn't think they're holding it wrong.

    We assert the doc names the M0 endpoints that DO work
    (``/healthz``, ``/env.js``) and explicitly mentions the gap
    (``404`` or ``M1``). The exact wording can drift; we only
    require these tokens to coexist.
    """
    body = DOC.read_text()
    assert "/healthz" in body, "M0 dev-server doc should name the working /healthz endpoint"
    assert "/env.js" in body, "M0 dev-server doc should name the working /env.js endpoint"
    # Either the literal "404" or "M1" appears as the gap-callout.
    assert "404" in body or "M1" in body, (
        "DEVELOPMENT.md should be honest that GET / is not wired in M0 (mention 404 or 'M1')"
    )
