"""Smoke tests for the Tailwind v3.4 wiring landed in iter 13.

Text/JSON-grep style — the Python test runner has no Node available,
so we don't exec PostCSS or Tailwind; we just enforce the shape of the
checked-in config so a regression surfaces in pytest rather than the
first time someone runs ``npm run dev``.

Pinning v3.x explicitly is load-bearing: Tailwind v4 has a different
API (CSS-first config via ``@import "tailwindcss"`` instead of the
three ``@tailwind`` directives, no ``tailwind.config.js`` required, no
``autoprefixer`` plugin in postcss.config.js). If a future iteration
bumps to v4 these tests must move with the new shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
TAILWIND_CONFIG = FRONTEND / "tailwind.config.js"
POSTCSS_CONFIG = FRONTEND / "postcss.config.js"
INDEX_CSS = FRONTEND / "src" / "index.css"
MAIN_TSX = FRONTEND / "src" / "main.tsx"
PACKAGE_JSON = FRONTEND / "package.json"


# ---------------------------------------------------------------------------
# tailwind.config.js
# ---------------------------------------------------------------------------


_CONTENT_ARRAY_RE = re.compile(r"content\s*:\s*\[(?P<body>[^\]]*)\]", re.DOTALL)
_STRING_LITERAL_RE = re.compile(r"""['"]([^'"]+)['"]""")


def _parse_tailwind_content_globs() -> list[str]:
    """Extract the ``content`` array entries from ``tailwind.config.js``.

    Tailwind's config is JS (not JSON), but the ``content`` field is a
    plain array of string literals — no spreads, no template strings,
    no computed values in any reasonable shadcn/ui or hand-written
    config. We tolerate either single or double quotes and ignore
    surrounding whitespace / inline comments inside the array. Asserts
    on the *parsed* array rather than substrings so additive evolution
    (e.g. shadcn/ui adding ``./components/**/*.{ts,tsx}``) doesn't break
    the test as long as the canonical project glob remains a member.
    """
    text = TAILWIND_CONFIG.read_text(encoding="utf-8")
    match = _CONTENT_ARRAY_RE.search(text)
    assert match is not None, "tailwind.config.js: could not locate `content: [ ... ]` array"
    body = match.group("body")
    return [m.group(1) for m in _STRING_LITERAL_RE.finditer(body)]


def _glob_scans_src_ts_tsx(glob: str) -> bool:
    """Does this glob entry scan ``./src`` recursively for both ``.ts``
    and ``.tsx`` files? Tolerates brace-expansion entries that include
    *additional* extensions (e.g. ``{js,ts,jsx,tsx,mdx}``), so a future
    shadcn/ui-style expansion remains acceptable as long as ts/tsx are
    still covered."""
    if not glob.startswith("./src/"):
        return False
    if "**" not in glob:
        return False
    if glob.endswith(".ts") or glob.endswith(".tsx"):
        # Split-glob form: caller checks both extensions separately.
        return True
    # Brace-expansion form: extract the {…} part and check membership.
    brace_match = re.search(r"\{([^}]+)\}", glob)
    if not brace_match:
        return False
    extensions = {ext.strip() for ext in brace_match.group(1).split(",")}
    return {"ts", "tsx"}.issubset(extensions)


def test_tailwind_config_content_array_includes_canonical_src_glob() -> None:
    """``content`` must contain at least one entry that scans
    ``./src/**`` for ``.ts`` and ``.tsx`` — otherwise JIT can't see
    class names referenced in TSX and the output stylesheet is silently
    empty.

    Asserts on the parsed array, not a literal substring, so shadcn/ui
    init (or any future tool) that *adds* additional content entries
    (e.g. ``./components/**/*.{ts,tsx}`` or ``./app/**/*.{ts,tsx}``) is
    accepted. Only a regression that *removes* the project's own
    ``./src/**`` scan should fail."""
    assert TAILWIND_CONFIG.exists(), "frontend/tailwind.config.js missing"
    globs = _parse_tailwind_content_globs()
    assert "./index.html" in globs, (
        f"tailwind.config.js content array must include './index.html'; got {globs!r}"
    )
    # Either a single brace-expansion entry covering both extensions,
    # or two split entries (one .ts and one .tsx).
    has_combined = any(_glob_scans_src_ts_tsx(g) and not g.endswith((".ts", ".tsx")) for g in globs)
    has_split = any(g.startswith("./src/") and "**" in g and g.endswith(".ts") for g in globs) and any(
        g.startswith("./src/") and "**" in g and g.endswith(".tsx") for g in globs
    )
    assert has_combined or has_split, (
        f"tailwind.config.js content array must scan ./src/** recursively "
        f"for both .ts and .tsx (either as a brace-expansion glob or two "
        f"split globs); got {globs!r}"
    )


# ---------------------------------------------------------------------------
# postcss.config.js
# ---------------------------------------------------------------------------


def test_postcss_config_exists_and_wires_tailwind_and_autoprefixer() -> None:
    """Vite picks up ``postcss.config.js`` automatically. The pipeline
    must include the Tailwind plugin (otherwise ``@tailwind`` directives
    pass through unprocessed) and Autoprefixer (matches the
    pd-prep-for-pgdp baseline)."""
    assert POSTCSS_CONFIG.exists(), "frontend/postcss.config.js missing"
    text = POSTCSS_CONFIG.read_text(encoding="utf-8")
    assert "tailwindcss" in text, "postcss.config.js must reference the `tailwindcss` plugin"
    assert "autoprefixer" in text, "postcss.config.js must reference the `autoprefixer` plugin"


# ---------------------------------------------------------------------------
# src/index.css — three @tailwind directives
# ---------------------------------------------------------------------------


def test_index_css_has_three_tailwind_directives() -> None:
    """v3 layer-injection points: ``@tailwind base; @tailwind components;
    @tailwind utilities;``. v4 replaces these with a single
    ``@import "tailwindcss"`` — if a future bump moves to v4 this test
    moves with it."""
    assert INDEX_CSS.exists(), "frontend/src/index.css missing"
    text = INDEX_CSS.read_text(encoding="utf-8")
    for directive in ("@tailwind base", "@tailwind components", "@tailwind utilities"):
        assert directive in text, (
            f"frontend/src/index.css missing required Tailwind v3 directive: {directive!r}"
        )


def test_index_css_defines_a_body_rule() -> None:
    """The ``body`` rule pins a deterministic font baseline so the smoke
    test (and future visual regressions) have something to assert.
    Without this, it's hard to tell whether the Tailwind pipeline ran
    at all vs. produced an empty stylesheet."""
    text = INDEX_CSS.read_text(encoding="utf-8")
    # Match `body {` with optional whitespace; tolerate a comment
    # leading line. Don't pin the exact font stack — only that a body
    # rule exists and references font-family.
    assert re.search(r"^\s*body\s*\{", text, flags=re.MULTILINE), (
        "frontend/src/index.css must define a `body { ... }` rule"
    )
    assert "font-family" in text, "frontend/src/index.css `body` rule must set font-family"


# ---------------------------------------------------------------------------
# src/main.tsx — must import the tailwind entry CSS
# ---------------------------------------------------------------------------


def test_main_tsx_imports_index_css() -> None:
    """If ``main.tsx`` doesn't import ``./index.css``, Vite's PostCSS
    pipeline never processes Tailwind and the page ships unstyled."""
    text = MAIN_TSX.read_text(encoding="utf-8")
    # Allow either single or double quotes; require the import is the
    # canonical relative path.
    pattern = re.compile(r"""import\s+["']\./index\.css["']\s*;?""")
    assert pattern.search(text), (
        'frontend/src/main.tsx must `import "./index.css"` so Vite\'s '
        "PostCSS pipeline processes the Tailwind directives."
    )


# ---------------------------------------------------------------------------
# package.json — devDependencies pinned to v3.x / v8.x / v10.x majors
# ---------------------------------------------------------------------------


def _semver_caret_major(spec: str) -> int | None:
    """Extract the major version from a caret range like ``^3.4.0``.
    Returns None if the spec is not in caret form."""
    match = re.match(r"^\^(\d+)\.", spec)
    return int(match.group(1)) if match else None


def test_package_json_pins_tailwind_postcss_autoprefixer_majors() -> None:
    """Pin the PostCSS trio to known-compatible majors:

    - ``tailwindcss`` v3 (NOT v4 — different API, see module docstring)
    - ``postcss`` v8 (Tailwind v3 peer-deps on postcss v8)
    - ``autoprefixer`` v10 (current major, matches pd-prep-for-pgdp)

    A future bump to v4 must move these pins and the @tailwind
    directive test together."""
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    dev_deps = pkg.get("devDependencies", {})

    expected = {
        "tailwindcss": 3,
        "postcss": 8,
        "autoprefixer": 10,
    }
    for name, major in expected.items():
        assert name in dev_deps, f"package.json devDependencies missing {name!r} (Tailwind wiring)"
        spec = dev_deps[name]
        actual_major = _semver_caret_major(spec)
        assert actual_major == major, (
            f"package.json devDependencies[{name!r}] must pin major v{major}.x "
            f"via caret range (e.g. ^{major}.x.y); got {spec!r}"
        )
