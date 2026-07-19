"""Settings contract — ``PDLABELER_*`` env prefix and field defaults.

Spec: ``docs/architecture/02-backend.md §3``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdomain_ocr_labeler_spa.settings import Settings


@pytest.mark.parametrize(
    ("field_name", "expected_default"),
    [
        # Server (docs/architecture/02-backend.md §3 lines 117-119)
        ("host", "127.0.0.1"),
        ("port", 8080),
        ("frontend_dev_url", None),
        # Logging (lines 119-120)
        ("log_format", "plain"),
        ("request_id_header", "X-Request-ID"),
        # Adapter axes (lines 126-128)
        ("storage_backend", "filesystem"),
        ("auth_mode", "none"),
        ("ocr_engine", "local_doctr"),
        # Project discovery (lines 131-132)
        ("source_projects_root", None),
        ("cli_project_dir", None),
        # Job runner (line 138) — consumer M3-deferred (B-63)
        ("poll_interval_seconds", 0.5),
        # OCR (lines 141-142) — consumers M3-deferred (B-63)
        ("hf_repo", "pdomain/pdomain-ocr-models"),
        ("no_prefetch", False),
        # Mode flag (line 144)
        ("mode", "normal"),
    ],
)
def test_settings_has_spec_section_3_fields_with_correct_defaults(
    monkeypatch: pytest.MonkeyPatch, field_name: str, expected_default: object
) -> None:
    """B-63 (iter 51): every field listed in ``docs/architecture/02-backend.md §3``
    must exist on ``Settings`` with the spec-stated default.

    Drift-pin test: if a future spec edit changes a default, this fails
    with the exact field name; if an impl edit drops a field, this
    fails on attribute access. Either way the spec and impl re-converge
    in one commit, not via a slow-burn drift filed weeks later.

    The path-shaped roots (config_root / data_root / cache_root) are
    NOT in this list — their defaults are derived from `~`/$XDG_* and
    are tested separately in `test_path_roots_default_under_user_home`
    (the values are env- and OS-dependent so a literal expected-default
    here would over-pin).
    """
    # Strip any inherited PDLABELER_* env so we observe true defaults.
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    s = Settings()
    assert hasattr(s, field_name), (
        f"Settings is missing spec-§3 field {field_name!r} — drift "
        "between docs/architecture/02-backend.md §3 and src/pdomain_ocr_labeler_spa/"
        "settings.py."
    )
    assert getattr(s, field_name) == expected_default, (
        f"Settings.{field_name} default = {getattr(s, field_name)!r}, spec §3 declares {expected_default!r}."
    )


def test_default_settings_have_expected_server_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # Strip any inherited PDLABELER_* env so we observe true defaults.
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    s = Settings()
    assert s.host == "127.0.0.1"
    assert s.port == 8080
    assert s.frontend_dev_url is None
    assert s.log_format == "plain"
    assert s.request_id_header == "X-Request-ID"
    assert s.mode == "normal"


def test_settings_reads_pdlabeler_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    # The ``PDLABELER_`` prefix is the spec's contract for every env var;
    # if this regresses, every deployment doc breaks.
    monkeypatch.setenv("PDLABELER_HOST", "0.0.0.0")
    monkeypatch.setenv("PDLABELER_PORT", "9090")
    monkeypatch.setenv("PDLABELER_LOG_FORMAT", "json")

    s = Settings()
    assert s.host == "0.0.0.0"
    assert s.port == 9090
    assert s.log_format == "json"


def test_settings_ignores_extra_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # ``extra="ignore"`` in the model_config protects against typoed env
    # vars killing startup. Future milestones will add fields; existing
    # PDLABELER_* env that doesn't match anything must not raise.
    monkeypatch.setenv("PDLABELER_TOTALLY_UNKNOWN_KNOB", "yes")
    Settings()  # must not raise


def test_path_roots_default_under_user_home() -> None:
    s = Settings()
    home = Path.home()
    assert s.config_root.is_absolute()
    assert s.data_root.is_absolute()
    assert s.cache_root.is_absolute()
    # Defaults live under $HOME — when users override via env, those are
    # respected; we only assert the default shape here.
    assert home in s.config_root.parents or s.config_root == home
    assert home in s.data_root.parents or s.data_root == home
    assert home in s.cache_root.parents or s.cache_root == home


def test_settings_accepts_explicit_overrides(tmp_path: Path) -> None:
    # The conftest ``settings`` fixture relies on this; make it explicit.
    s = Settings(
        host="127.0.0.1",
        port=8123,
        data_root=tmp_path / "d",
        config_root=tmp_path / "c",
        cache_root=tmp_path / "ca",
        mode="api_only",
    )
    assert s.port == 8123
    assert s.data_root == tmp_path / "d"
    assert s.mode == "api_only"


def test_settings_is_frozen_post_construction() -> None:
    """Spec §3 (docs/architecture/02-backend.md:148-149): "override after construction
    is forbidden."

    Regression for B-04: M0 ``__main__.py`` previously mutated
    ``settings.frontend_dev_url`` after constructing ``Settings()``. With
    ``frozen=True`` enabled in ``model_config``, any such regression now
    fails loudly at the call-site instead of silently desyncing process
    state. Verifies for at least ``frontend_dev_url`` (the field that
    motivated the bug) plus ``host`` and ``port`` (the other fields the
    CLI threads through).
    """
    from pydantic import ValidationError

    s = Settings()
    for field in ("frontend_dev_url", "host", "port"):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(s, field, "x" if field != "port" else 9999)


def test_main_does_not_mutate_settings_post_construction() -> None:
    """B-04 belt-and-suspenders: assert via AST that ``__main__.py`` does
    not reintroduce the ``settings.<field> = …`` pattern.

    Even with ``frozen=True`` catching a runtime regression, a static
    check guards against someone disabling frozen later (M2 might need
    to, when wiring an ``api_key`` reload signal) without auditing this
    call-site.
    """
    import ast
    import inspect

    from pdomain_ocr_labeler_spa import __main__ as main_mod

    src = inspect.getsource(main_mod)
    tree = ast.parse(src)
    bad_assignments: list[str] = []

    def _is_settings_attr(node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "settings"
        )

    for node in ast.walk(tree):
        # ``settings.foo = ...``
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if _is_settings_attr(target):
                    bad_assignments.append(
                        f"settings.{target.attr} = ... at line {node.lineno}"  # type: ignore[attr-defined]
                    )
        # ``settings.foo += ...`` and friends (B-13)
        elif isinstance(node, ast.AugAssign):
            if _is_settings_attr(node.target):
                bad_assignments.append(
                    f"settings.{node.target.attr} <op>= ... at line {node.lineno}"  # type: ignore[attr-defined]
                )
        # ``settings.foo: int = ...`` (B-13)
        elif isinstance(node, ast.AnnAssign):  # noqa: SIM102  # elif branch: comment on this line explains AnnAssign form; body guard is separate concern
            if _is_settings_attr(node.target):
                bad_assignments.append(
                    f"settings.{node.target.attr}: ... = ... at line {node.lineno}"  # type: ignore[attr-defined]
                )
    assert not bad_assignments, (
        f"post-construction settings mutation reintroduced (spec §3 forbids): {bad_assignments}"
    )


def test_ast_scanner_catches_all_three_assignment_forms() -> None:
    """B-13 self-test for the AST scanner above.

    The static check in
    ``test_main_does_not_mutate_settings_post_construction`` must
    catch all three mutation forms — ``Assign``, ``AugAssign``,
    ``AnnAssign`` — targeting ``settings.<attr>``. The runtime
    ``frozen=True`` catches all three, but the static net is the
    backup; the iter-10 review found the original walker only matched
    ``Assign``. This test feeds each shape through the same walker
    logic to guarantee the holes are closed.
    """
    import ast

    snippets = {
        "Assign": "settings.host = '0.0.0.0'\n",
        "AugAssign": "settings.port += 1\n",
        "AnnAssign": "settings.port: int = 9090\n",
    }

    def _is_settings_attr(node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "settings"
        )

    for label, src in snippets.items():
        tree = ast.parse(src)
        flagged = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                flagged = flagged or any(_is_settings_attr(t) for t in node.targets)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                flagged = flagged or _is_settings_attr(node.target)
        assert flagged, f"AST scanner missed {label} form: {src!r}"


def test_settings_undo_depth_default_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec 2026-06-12-event-store-undo slice H-D: ``PDLABELER_UNDO_DEPTH``.

    Default 50 (U-8); env-overridable like every other Settings knob.
    """
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    assert Settings().undo_depth == 50

    monkeypatch.setenv("PDLABELER_UNDO_DEPTH", "7")
    assert Settings().undo_depth == 7


def test_settings_ocr_timeout_s_default_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the OCR timeout contract in ``docs/architecture/02-backend.md``.

    Default 900.0 seconds; env-overridable; <=0 disables the timeout.
    """
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    assert Settings().ocr_timeout_s == 900.0

    monkeypatch.setenv("PDLABELER_OCR_TIMEOUT_S", "30")
    assert Settings().ocr_timeout_s == 30.0

    monkeypatch.setenv("PDLABELER_OCR_TIMEOUT_S", "0")
    assert Settings().ocr_timeout_s == 0.0


def test_settings_max_concurrent_ocr_jobs_default_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the OCR concurrency contract in ``docs/architecture/02-backend.md``.

    Default 1; env-overridable; <=0 disables the cap.
    """
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    assert Settings().max_concurrent_ocr_jobs == 1

    monkeypatch.setenv("PDLABELER_MAX_CONCURRENT_OCR_JOBS", "4")
    assert Settings().max_concurrent_ocr_jobs == 4

    monkeypatch.setenv("PDLABELER_MAX_CONCURRENT_OCR_JOBS", "0")
    assert Settings().max_concurrent_ocr_jobs == 0
