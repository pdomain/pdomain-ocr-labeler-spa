"""Smoke tests for the Tailwind 4 wiring.

Text/JSON-grep style — the Python test runner has no Node available, so we
don't exec PostCSS or Tailwind; we just enforce the shape of the checked-in
config so a regression surfaces in pytest rather than the first time someone
runs ``pnpm dev``.

Tailwind 4 moved the configuration into CSS. There is no ``tailwind.config.js``
any more: the content scan is automatic, and the theme lives in an ``@theme``
block in ``src/index.css``. The three ``@tailwind`` directives collapsed into a
single ``@import "tailwindcss"``, the PostCSS plugin moved to its own
``@tailwindcss/postcss`` package, and ``autoprefixer`` left the pipeline
because Tailwind 4 prefixes on its own.

These tests were written against v3 and moved with the v4 bump, which is what
their original module docstring asked whoever did the bump to do.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
POSTCSS_CONFIG = FRONTEND / "postcss.config.js"
INDEX_CSS = FRONTEND / "src" / "index.css"
MAIN_TSX = FRONTEND / "src" / "main.tsx"
PACKAGE_JSON = FRONTEND / "package.json"


def _semver_caret_major(spec: str) -> int | None:
    """Return the major version pinned by a caret range like ``^4.3.3``."""
    match = re.match(r"^\^?(\d+)\.", spec.strip())
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# No tailwind.config.js — the theme lives in CSS now
# ---------------------------------------------------------------------------


def test_tailwind_config_file_is_gone() -> None:
    """Tailwind 4 needs no config file, and leaving a stale one behind is
    worse than having none: it looks authoritative while nothing reads it."""
    for name in ("tailwind.config.js", "tailwind.config.ts", "tailwind.config.mjs"):
        assert not (FRONTEND / name).exists(), (
            f"frontend/{name} should have been removed by the Tailwind 4 migration — "
            "the theme now lives in the @theme block in src/index.css"
        )


# ---------------------------------------------------------------------------
# postcss.config.js
# ---------------------------------------------------------------------------


def test_postcss_config_uses_the_tailwind_four_plugin() -> None:
    """Vite picks up ``postcss.config.js`` automatically. Tailwind 4 ships its
    plugin as ``@tailwindcss/postcss``; the bare ``tailwindcss`` entry that
    worked under v3 is no longer a PostCSS plugin at all, and leaves the CSS
    unprocessed. Autoprefixer must be gone, since Tailwind 4 prefixes itself."""
    assert POSTCSS_CONFIG.exists(), "frontend/postcss.config.js missing"
    text = POSTCSS_CONFIG.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("//"))
    assert "@tailwindcss/postcss" in code, (
        "postcss.config.js must reference the `@tailwindcss/postcss` plugin"
    )
    assert "autoprefixer" not in code, (
        "postcss.config.js must not reference `autoprefixer` — Tailwind 4 prefixes itself"
    )


# ---------------------------------------------------------------------------
# src/index.css — one @import, plus the @theme block
# ---------------------------------------------------------------------------


def test_index_css_imports_tailwind_once() -> None:
    """Tailwind 4 replaces the three v3 layer-injection directives with a
    single ``@import "tailwindcss"``."""
    assert INDEX_CSS.exists(), "frontend/src/index.css missing"
    text = INDEX_CSS.read_text(encoding="utf-8")
    assert re.search(r"""@import\s+['"]tailwindcss['"]""", text), (
        "frontend/src/index.css must contain a single @import of 'tailwindcss'"
    )
    for directive in ("@tailwind base", "@tailwind components", "@tailwind utilities"):
        assert directive not in text, (
            f"frontend/src/index.css still carries the Tailwind 3 directive {directive!r}; "
            "Tailwind 4 replaces all three with @import 'tailwindcss'"
        )


def test_index_css_defines_the_theme_tokens() -> None:
    """The palette moved out of tailwind.config.js and into an ``@theme``
    block. Without it the ``bg-page`` / ``ink-1`` style utilities silently
    stop resolving, which is exactly the regression this file exists to
    catch."""
    text = INDEX_CSS.read_text(encoding="utf-8")
    assert "@theme" in text, "frontend/src/index.css must define an @theme block"
    for token in ("--color-bg-page", "--color-ink-1", "--color-accent"):
        assert token in text, (
            f"frontend/src/index.css @theme block missing {token!r} — "
            "the corresponding utility class will not resolve"
        )


def test_main_tsx_imports_index_css() -> None:
    """The stylesheet has to be imported somewhere or none of it ships."""
    assert MAIN_TSX.exists(), "frontend/src/main.tsx missing"
    text = MAIN_TSX.read_text(encoding="utf-8")
    assert re.search(r"""import\s+['"]\./index\.css['"]""", text), (
        "frontend/src/main.tsx must import './index.css'"
    )


# ---------------------------------------------------------------------------
# package.json pins
# ---------------------------------------------------------------------------


def test_package_json_pins_the_tailwind_four_majors() -> None:
    """Pin the PostCSS pair to known-compatible majors: ``tailwindcss`` 4 and
    its own ``@tailwindcss/postcss`` plugin at the same major. ``autoprefixer``
    must be absent."""
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    dev_deps = pkg.get("devDependencies", {})

    for name in ("tailwindcss", "@tailwindcss/postcss"):
        assert name in dev_deps, f"package.json devDependencies missing {name!r} (Tailwind wiring)"
        actual_major = _semver_caret_major(dev_deps[name])
        assert actual_major == 4, (
            f"package.json devDependencies[{name!r}] must pin major v4.x "
            f"via caret range; got {dev_deps[name]!r}"
        )

    assert "autoprefixer" not in dev_deps, (
        "package.json must not depend on `autoprefixer` — Tailwind 4 prefixes itself"
    )
