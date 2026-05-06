"""Smoke tests for ``frontend/`` config files.

Pin the iter-8 fixes for B-05 (dangling eslint lint script), B-06
(openapi-gen path drift between Makefile / package.json / spec) and
B-08 (production tsconfig leaking test files into ``tsc -b`` build).

These are text/JSON-grep tests — same shape as ``test_vite_config.py``,
``test_makefile.py`` and ``test_pre_commit_config.py``. The Python
test runner has no Node available, so we don't exec npm; we just
enforce the shape of the checked-in config so a regression surfaces
in pytest rather than the first time someone runs ``npm run …``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
PACKAGE_JSON = FRONTEND / "package.json"
TSCONFIG_APP = FRONTEND / "tsconfig.app.json"
TSCONFIG_TEST = FRONTEND / "tsconfig.test.json"
VITEST_CONFIG = FRONTEND / "vitest.config.ts"
MAKEFILE = REPO_ROOT / "Makefile"

# Canonical openapi-typescript output path, repeated by Makefile +
# package.json + spec. Source of truth: ``specs/01-data-models.md:712``
# ("openapi-typescript openapi.json -o src/api/types.ts" — relative to
# ``frontend/``) and ``specs/15-deployment-dev.md:127`` ("writes
# frontend/openapi.json + frontend/src/api/types.ts").
EXPECTED_TS_TYPES = "src/api/types.ts"
EXPECTED_OPENAPI_INPUT = "openapi.json"  # relative to frontend/


def _load_jsonc(path: Path) -> dict:
    """Tolerant JSON loader for tsconfig files (which may contain
    line comments). Strip ``//`` line-comments before json.loads."""
    raw = path.read_text(encoding="utf-8")
    stripped = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)
    return json.loads(stripped)


# ---------------------------------------------------------------------------
# B-05 — eslint lint script must not be declared without eslint installed
# ---------------------------------------------------------------------------


def test_package_json_does_not_declare_unrunnable_eslint_script() -> None:
    """B-05: ``npm run lint`` invoked eslint, but eslint was not in
    ``devDependencies``. Iter 8 dropped the script entirely (pending
    a real eslint config landing in a later M0 sub-task — see
    OPEN_QUESTIONS Q-A9). If a future iteration re-adds the script,
    eslint must be in ``devDependencies`` at the same time."""
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    scripts = pkg.get("scripts", {})
    dev_deps = pkg.get("devDependencies", {})
    if "lint" in scripts:
        # If the script exists, eslint must be installed.
        assert "eslint" in dev_deps, (
            "package.json declares `lint` script but eslint is missing "
            "from devDependencies (B-05 regression — see "
            "docs/BUGS_FOUND.md)."
        )


# ---------------------------------------------------------------------------
# B-06 — single canonical openapi-gen output path
# ---------------------------------------------------------------------------


def test_openapi_gen_path_is_consistent_across_makefile_and_package_json() -> None:
    """B-06: ``frontend/package.json`` had ``../openapi.json`` while
    Makefile writes ``frontend/openapi.json`` and reads
    ``openapi.json`` from inside ``frontend/``. After fix, both must
    consume the same path (``openapi.json`` relative to ``frontend/``)
    and emit to the same ``src/api/types.ts``.
    """
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    openapi_script = pkg["scripts"]["openapi:gen"]
    # Must read from frontend-local openapi.json (NOT ../openapi.json).
    assert "../openapi.json" not in openapi_script, (
        "package.json openapi:gen still reads ../openapi.json "
        "(B-06 regression — Makefile writes frontend/openapi.json)."
    )
    assert " openapi.json " in f" {openapi_script} ", (
        f"package.json openapi:gen must read `openapi.json` (frontend-local); got: {openapi_script!r}"
    )
    assert EXPECTED_TS_TYPES in openapi_script, (
        f"package.json openapi:gen must emit to {EXPECTED_TS_TYPES!r}; got: {openapi_script!r}"
    )

    makefile_text = MAKEFILE.read_text(encoding="utf-8")
    # Makefile writes the schema to frontend/openapi.json and runs
    # openapi-typescript with the same EXPECTED_TS_TYPES output.
    assert "frontend/openapi.json" in makefile_text, (
        "Makefile no longer writes frontend/openapi.json (B-06 canonical path drift)."
    )
    assert f"-o {EXPECTED_TS_TYPES}" in makefile_text, (
        f"Makefile openapi-export must emit -o {EXPECTED_TS_TYPES}; canonical path drift."
    )

    # Spec keeps the same canonical path — guards against the spec
    # drifting away from code without us noticing.
    spec_text = (REPO_ROOT / "specs" / "01-data-models.md").read_text(encoding="utf-8")
    assert f"openapi-typescript openapi.json -o {EXPECTED_TS_TYPES}" in spec_text, (
        "specs/01-data-models.md no longer documents the canonical openapi-typescript invocation."
    )


# ---------------------------------------------------------------------------
# B-08 — production tsconfig must NOT include test files
# ---------------------------------------------------------------------------


def test_tsconfig_app_excludes_test_files() -> None:
    """B-08: ``tsc -b`` (the production build) must not type-check
    ``*.test.{ts,tsx}``, ``*.spec.{ts,tsx}``, ``__tests__/**`` or
    ``src/test/**`` (vitest setup). Otherwise prod build picks up
    vitest globals + jest-dom matchers and fails strict checks once
    the first non-trivial test lands.
    """
    cfg = _load_jsonc(TSCONFIG_APP)
    excludes = cfg.get("exclude", [])
    # Required exclude patterns — set comparison so order doesn't matter.
    required = {
        "src/**/*.test.ts",
        "src/**/*.test.tsx",
        "src/**/*.spec.ts",
        "src/**/*.spec.tsx",
        "src/**/__tests__/**",
        "src/test/**",
    }
    missing = required - set(excludes)
    assert not missing, (
        f"tsconfig.app.json exclude is missing required test-file patterns: {missing}. "
        "Production build must not type-check test files (B-08)."
    )


def test_tsconfig_test_exists_and_includes_test_files() -> None:
    """B-08: A test-only tsconfig must exist and pick up the patterns
    excluded from ``tsconfig.app.json`` so editors / vitest type-check
    have somewhere coherent to look."""
    assert TSCONFIG_TEST.exists(), (
        "tsconfig.test.json missing — required by B-08 fix to host "
        "vitest globals + test-file include patterns."
    )
    cfg = _load_jsonc(TSCONFIG_TEST)
    assert cfg.get("extends") == "./tsconfig.app.json", (
        "tsconfig.test.json must extend ./tsconfig.app.json so prod "
        "compiler options (strict etc.) stay shared."
    )
    includes = set(cfg.get("include", []))
    expected = {
        "src/**/*.test.ts",
        "src/**/*.test.tsx",
        "src/**/*.spec.ts",
        "src/**/*.spec.tsx",
        "src/**/__tests__/**",
        "src/test/**",
    }
    missing = expected - includes
    assert not missing, f"tsconfig.test.json include is missing required test-file patterns: {missing}."


def test_vitest_config_references_test_tsconfig() -> None:
    """B-08: ``vitest.config.ts`` must wire ``typecheck.tsconfig`` to
    ``./tsconfig.test.json`` so ``vitest typecheck`` reads the test-only
    typings rather than the prod-only app tsconfig."""
    text = VITEST_CONFIG.read_text(encoding="utf-8")
    assert "tsconfig.test.json" in text, (
        "vitest.config.ts no longer references tsconfig.test.json (B-08 wiring regression)."
    )
