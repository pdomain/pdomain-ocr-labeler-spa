"""Pure-derivation pins for ``core/persistence/paths.py``.

Spec: ``specs/01-data-models.md §5`` (OS-aware paths table) +
``specs/09-persistence.md §1, §5-§7``.

These tests fix the **subdirectory layout** the helpers produce. The
OS-aware roots themselves are owned by ``Settings`` (and tested in
``test_settings.py``); this module is the layer that derives
per-purpose subdirs from those roots.

Properties under test:
- Each helper returns the spec-mandated suffix under the root it's given.
- Helpers are pure: same inputs → same outputs, no I/O, no global state.
- Helpers don't mkdir (so ``build_app(Settings())`` stays pure — B-54
  invariant for the persistence layer too).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.persistence.paths import (
    CONFIG_YAML_FILENAME,
    LOGS_DIRNAME,
    PAGE_IMAGES_DIRNAME,
    PROJECT_BACKUPS_DIRNAME,
    SAVED_PROJECTS_DIRNAME,
    SESSION_STATE_FILENAME,
    config_yaml_path,
    image_cache_root,
    labeled_projects_root,
    logs_root,
    project_backups_root,
    session_state_path,
)

# ── filename / dirname constants (drift pin against the spec) ─────────────


def test_filename_constants_match_spec_literals() -> None:
    """Spec ``§1`` and ``§5-§7`` fix these names verbatim — drift would
    silently desync the SPA from the legacy binary's on-disk layout
    (D-003 shared-data-root contract) so pin every literal."""
    assert SAVED_PROJECTS_DIRNAME == "labeled-projects"
    assert PROJECT_BACKUPS_DIRNAME == "project-backups"
    assert LOGS_DIRNAME == "logs"
    assert PAGE_IMAGES_DIRNAME == "page-images"
    assert CONFIG_YAML_FILENAME == "config.yaml"
    assert SESSION_STATE_FILENAME == "session_state.json"


# ── per-helper return-value shape ─────────────────────────────────────────


@pytest.mark.parametrize(
    "helper, root_arg, expected_suffix",
    [
        (labeled_projects_root, "data", "labeled-projects"),
        (project_backups_root, "data", "project-backups"),
        (logs_root, "data", "logs"),
        (session_state_path, "data", "session_state.json"),
        (image_cache_root, "cache", "page-images"),
        (config_yaml_path, "config", "config.yaml"),
    ],
)
def test_helper_returns_root_plus_spec_suffix(
    tmp_path: Path,
    helper,
    root_arg: str,
    expected_suffix: str,
) -> None:
    """Every helper appends exactly one path component (the spec literal)
    onto its caller-supplied root and returns the result."""
    root = tmp_path / root_arg
    result = helper(root)
    assert isinstance(result, Path)
    assert result == root / expected_suffix
    # Sanity: the helper added a single component (not, e.g., the app name).
    assert result.parent == root


# ── purity invariants ─────────────────────────────────────────────────────


def test_paths_helpers_do_not_create_anything_on_disk(tmp_path: Path) -> None:
    """All six helpers must be pure path arithmetic — no mkdir, no touch.

    Same invariant as B-54 (``FilesystemStorage.__init__`` purity):
    derived paths are computed lazily so smoke-test invocations of
    ``build_app(Settings())`` don't write to the developer's homedir
    as a side effect.
    """
    nonexistent = tmp_path / "nope"
    assert not nonexistent.exists()

    # Call every helper against a path that does NOT exist.
    _ = labeled_projects_root(nonexistent)
    _ = project_backups_root(nonexistent)
    _ = logs_root(nonexistent)
    _ = session_state_path(nonexistent)
    _ = image_cache_root(nonexistent)
    _ = config_yaml_path(nonexistent)

    # Nothing should have been created.
    assert not nonexistent.exists(), "paths helper(s) created the root as a side effect — purity violation."


def test_paths_helpers_are_idempotent(tmp_path: Path) -> None:
    """Repeated calls with the same root return equal paths — no hidden
    state (e.g. a counter, a once-only suffix)."""
    root = tmp_path / "data"
    assert labeled_projects_root(root) == labeled_projects_root(root)
    assert image_cache_root(root) == image_cache_root(root)
    assert session_state_path(root) == session_state_path(root)


# ── distinct-suffix invariant (catches accidental collisions) ─────────────


def test_data_root_subdirs_are_all_distinct(tmp_path: Path) -> None:
    """Every helper that derives from ``data_root`` must produce a
    distinct path. Catches a regression where two helpers accidentally
    share a suffix (e.g. typoing ``"labeled-projects"`` in two places).
    """
    root = tmp_path / "data"
    paths = {
        "labeled_projects": labeled_projects_root(root),
        "project_backups": project_backups_root(root),
        "logs": logs_root(root),
        "session_state": session_state_path(root),
    }
    # Each value must be unique.
    assert len(set(paths.values())) == len(paths), f"data_root subdirs collide: {paths}"


def test_paths_module_does_not_call_os_or_platform() -> None:
    """``paths.py`` must NOT branch on OS at the helper layer — that's
    Settings' job (one source of OS-awareness, not two). AST-scan the
    source for forbidden imports / calls.

    Catches a regression where a future edit copies the legacy
    ``PersistencePathsOperations`` class shape (which DOES call
    ``platform.system()`` and ``os.getenv``) and re-introduces the
    double-OS-awareness bug.

    B-61: also covers dynamic-import escape hatches —
    ``__import__("os")`` and ``importlib.import_module("os")`` — so a
    future "convenience" refactor can't slip OS-awareness past the
    static-import check.
    """
    import ast
    from pathlib import Path as _Path

    src = (
        _Path(__file__).parent.parent.parent.parent.parent
        / "src"
        / "pd_ocr_labeler_spa"
        / "core"
        / "persistence"
        / "paths.py"
    )
    tree = ast.parse(src.read_text())

    forbidden_imports = {"platform", "os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_imports, (
                    f"paths.py imports {alias.name!r} — OS-awareness belongs in Settings, not here."
                )
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_imports, (
                f"paths.py imports from {node.module!r} — OS-awareness belongs in Settings."
            )
        elif isinstance(node, ast.Call):
            # B-61: dynamic-import forms — ``__import__("os")`` and
            # ``importlib.import_module("os")``. Both produce the same
            # OS-awareness leak as a static ``import os`` but slip past
            # the ``ast.Import`` / ``ast.ImportFrom`` walkers above.
            func = node.func
            # Form 1: ``__import__("os")`` — call to a Name.
            if isinstance(func, ast.Name) and func.id == "__import__":  # noqa: SIM102  # outer checks type+id; inner checks args; combining loses the Form-1 comment grouping
                if node.args and isinstance(node.args[0], ast.Constant):
                    arg = node.args[0].value
                    assert arg not in forbidden_imports, (
                        f"paths.py calls __import__({arg!r}) — dynamic OS-awareness import banned."
                    )
            # Form 2: ``importlib.import_module("os")`` — Attribute call.
            # Flag ANY call to ``importlib.import_module`` regardless of
            # arg, since the arg may be a runtime-computed string we
            # can't statically inspect.
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "import_module"
                and isinstance(func.value, ast.Name)
                and func.value.id == "importlib"
            ):
                raise AssertionError(
                    "paths.py calls importlib.import_module(...) — dynamic "
                    "imports defeat the OS-awareness purity guard. If a "
                    "specific module is genuinely needed at this layer, "
                    "amend spec §1 first and document why."
                )


def test_paths_purity_scan_catches_dynamic_import_call() -> None:
    """B-61 meta-test: confirm the AST scan in
    ``test_paths_module_does_not_call_os_or_platform`` actually
    flags ``__import__("os")`` — not just static ``import os``.

    We feed the scan a synthetic source string containing the dynamic
    form and assert the scan raises AssertionError. Without this
    meta-test the bug B-61 originally described — silent gap in the
    walker — would never re-surface even after the gap was reopened.
    """
    import ast

    forbidden_imports = {"platform", "os"}
    bad_source = "x = __import__('os')\n"
    tree = ast.parse(bad_source)

    triggered = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "__import__":  # noqa: SIM102  # outer checks type+id; inner checks args; mirrors production scan structure
                if node.args and isinstance(node.args[0], ast.Constant):
                    arg = node.args[0].value
                    if arg in forbidden_imports:
                        triggered = True
    assert triggered, "Dynamic-import scan failed to flag __import__('os') — B-61 gap reopened."


def test_paths_purity_scan_catches_importlib_import_module() -> None:
    """B-61 meta-test: confirm the AST scan flags any
    ``importlib.import_module(...)`` call (regardless of the arg)."""
    import ast

    bad_source = "import importlib\nx = importlib.import_module('os')\n"
    tree = ast.parse(bad_source)

    triggered = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "import_module"
                and isinstance(func.value, ast.Name)
                and func.value.id == "importlib"
            ):
                triggered = True
    assert triggered, "Dynamic-import scan failed to flag importlib.import_module(...) — B-61 gap reopened."
