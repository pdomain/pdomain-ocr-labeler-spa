"""Pin the shape of `pd_ocr_labeler_spa.__version__`.

B-11 background: hatch-vcs writes a frozen version string into dist-info
metadata at install time, and the import-side `__version__` is read from
that metadata. The post-commit hook in `.pre-commit-config.yaml` keeps
the install fresh so `__version__` doesn't drift across iterations
(test for that lives in `test_pre_commit_config.py`).

What this module guards is the *resolution path*: `__init__.py` must
read from `importlib.metadata.version("pd-ocr-labeler-spa")` (with a
`PackageNotFoundError` fallback) — never a hard-coded string. Drift
back to a literal would silently survive `make refresh-version`, since
the literal wouldn't be recomputed at all.
"""

from __future__ import annotations

import ast
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pd_ocr_labeler_spa

INIT_PATH = Path(pd_ocr_labeler_spa.__file__)


def test_version_matches_installed_metadata() -> None:
    """Runtime invariant: `__version__` is whatever
    `importlib.metadata.version` says — not a literal that could drift.

    Asserts both halves: (a) we can get a version through
    importlib.metadata for the installed package, and (b) the package's
    `__version__` is byte-identical to it. If the package isn't
    installed at all, the fallback path (`0.0.0+unknown`) is acceptable
    and we skip equality.
    """
    try:
        metadata_version = version("pd-ocr-labeler-spa")
    except PackageNotFoundError:
        # Editable install missing dist-info — accept the fallback shape.
        assert pd_ocr_labeler_spa.__version__ == "0.0.0+unknown"
        return
    assert pd_ocr_labeler_spa.__version__ == metadata_version, (
        "__version__ must come from importlib.metadata.version, not a hard-coded literal — see B-11 / iter 12"
    )


def test_init_does_not_hard_code_version_literal() -> None:
    """Static guard: walk `__init__.py` and ensure `__version__` is
    only ever assigned from a `version("pd-ocr-labeler-spa")` call (or
    the fallback string inside an `except PackageNotFoundError` block).

    The exemption: a literal assignment is allowed only when its parent
    is an `except PackageNotFoundError` handler — that's the documented
    fallback shape and removing it would crash on missing dist-info.
    """
    src = INIT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Map child -> parent for context-sensitive checks.
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def _under_packagenotfound_handler(node: ast.AST) -> bool:
        cur = parents.get(node)
        while cur is not None:
            if isinstance(cur, ast.ExceptHandler):
                t = cur.type
                if isinstance(t, ast.Name) and t.id == "PackageNotFoundError":
                    return True
                if isinstance(t, ast.Tuple) and any(
                    isinstance(e, ast.Name) and e.id == "PackageNotFoundError" for e in t.elts
                ):
                    return True
            cur = parents.get(cur)
        return False

    version_assignments: list[ast.Assign] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = node.targets
        if not (len(targets) == 1 and isinstance(targets[0], ast.Name) and targets[0].id == "__version__"):
            continue
        version_assignments.append(node)

    assert version_assignments, "no `__version__ = ...` found in __init__.py"

    saw_dynamic = False
    for assign in version_assignments:
        rhs = assign.value
        if isinstance(rhs, ast.Call):
            func = rhs.func
            is_version_call = (isinstance(func, ast.Name) and func.id == "version") or (
                isinstance(func, ast.Attribute) and func.attr == "version"
            )
            if is_version_call:
                saw_dynamic = True
                continue
        if isinstance(rhs, ast.Constant) and isinstance(rhs.value, str):
            assert _under_packagenotfound_handler(assign), (
                "__version__ may only be assigned a literal string inside "
                "an `except PackageNotFoundError:` block (the documented "
                "fallback). Drop static literals elsewhere — see B-11."
            )
            continue
        raise AssertionError(
            f"unexpected RHS for `__version__` assignment at line {assign.lineno}: "
            f"{ast.dump(rhs)} — expected version() call or fallback literal"
        )

    assert saw_dynamic, (
        "__init__.py must contain at least one `__version__ = version(...)` "
        "assignment so the version is resolved dynamically from "
        "importlib.metadata"
    )
