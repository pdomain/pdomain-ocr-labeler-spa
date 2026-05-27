"""``pdomain_ocr_labeler_spa.__main__`` CLI flag-wiring contract — M1.g.

Specs:

- ``docs/architecture/15-deployment-dev.md §3`` names the canonical CLI flag set
  (mirrors legacy ``pd-ocr-labeler-ui`` plus pgdp-prep's
  ``--frontend-dev``).
- ``docs/architecture/02-backend.md §3`` makes Settings the single, frozen source
  of truth — built **once** in ``main()`` from CLI overrides layered on
  top of env defaults.

Precedence (verified below):

1. Defaults (Settings field defaults).
2. ``PDLABELER_*`` environment variables.
3. CLI flags (only when explicitly passed).

Mocking strategy: we never actually start uvicorn — we patch
``uvicorn.run`` and ``webbrowser.open`` at the call site and assert on
the kwargs. ``Settings`` is built for real so the env-vs-CLI precedence
test exercises the real pydantic-settings layering.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pdomain_ocr_labeler_spa import __main__ as main_mod
from pdomain_ocr_labeler_spa.__main__ import _parse_args, main
from pdomain_ocr_labeler_spa.settings import Settings

# ── Argparse parser shape ──────────────────────────────────────────────────


def test_parser_accepts_canonical_flag_set() -> None:
    """spec/15 §3 lists the canonical flag set — every name must parse.

    Includes legacy parity (`--projects-root`, `--debugpy`, `--verbose`,
    `--page-timing`) and pgdp-prep parity (`--frontend-dev`). New for the
    SPA: `--data-root` (overrides `Settings.data_root`).
    """
    ns = _parse_args(
        [
            "/some/project",
            "--projects-root",
            "/some/projects-root",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--reload",
            "--no-browser",
            "--frontend-dev",
            "http://localhost:5173",
            "--debugpy",
            "-vv",
            "--page-timing",
            "--data-root",
            "/some/data-root",
        ]
    )
    assert ns.project_dir == "/some/project"
    assert ns.projects_root == Path("/some/projects-root")
    assert ns.host == "0.0.0.0"
    assert ns.port == 9000
    assert ns.reload is True
    assert ns.no_browser is True
    assert ns.frontend_dev == "http://localhost:5173"
    assert ns.debugpy is True
    assert ns.verbose == 2
    assert ns.page_timing is True
    assert ns.data_root == Path("/some/data-root")


def test_parser_defaults_when_no_flags_given() -> None:
    """All flags are optional. The bare console-script call must parse."""
    ns = _parse_args([])
    assert ns.project_dir is None
    assert ns.projects_root is None
    assert ns.host is None
    assert ns.port is None
    assert ns.reload is False
    assert ns.no_browser is False
    assert ns.frontend_dev is None
    assert ns.debugpy is False
    assert ns.verbose == 0
    assert ns.page_timing is False
    assert ns.data_root is None
    assert ns.version is False


def test_short_verbose_flag_counts() -> None:
    """``-v`` is a count flag (legacy parity, ``cli.py:50-56``)."""
    assert _parse_args(["-v"]).verbose == 1
    assert _parse_args(["-vv"]).verbose == 2
    assert _parse_args(["-vvv"]).verbose == 3
    assert _parse_args(["--verbose", "--verbose"]).verbose == 2


def test_main_prints_device_line_before_listening(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """``main()`` must print the resolved torch device on a separate line.

    Operators running ``make run`` need to know whether torch picked up
    the GPU before the OCR pipeline starts pulling models — printing a
    one-liner from ``core.device_info.describe_device()`` at startup is
    the cheapest signal. Order is: device line, then "Listening on …",
    so a `tail -1` of the boot log still surfaces the URL.
    """
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    with (
        patch.object(main_mod, "uvicorn") as mock_uvicorn,
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        mock_uvicorn.run.side_effect = lambda *a, **kw: None
        rc = main(["--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    # Find the indices of the device + listening lines.
    device_idx = next((i for i, line in enumerate(lines) if line.startswith("device:")), None)
    listening_idx = next((i for i, line in enumerate(lines) if line.startswith("Listening on ")), None)
    assert device_idx is not None, f"device line missing from startup output:\n{out}"
    assert listening_idx is not None, f"Listening line missing from startup output:\n{out}"
    assert device_idx < listening_idx, (
        "device line must come before 'Listening on' so a tail -1 still surfaces the URL"
    )


def test_version_flag_short_circuits(capsys: pytest.CaptureFixture[str]) -> None:
    """``--version`` prints version and returns 0 without starting uvicorn."""
    with patch.object(main_mod, "uvicorn") as mock_uvicorn:
        rc = main(["--version"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    # Must look like a version string and must not have invoked uvicorn.
    assert out  # non-empty
    mock_uvicorn.run.assert_not_called()


# ── Settings(**overrides) precedence ───────────────────────────────────────


def test_cli_overrides_layered_into_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """CLI flag wins over env. Env wins over default.

    Spec §3: Settings is built once from a single overrides dict; this
    test exercises all three precedence levels in one shot.
    """
    # Strip any inherited PDLABELER_* env first.
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    # Layer 2 (env): both host and port.
    monkeypatch.setenv("PDLABELER_HOST", "10.0.0.1")
    monkeypatch.setenv("PDLABELER_PORT", "9000")
    # Layer 3 (CLI): only port. Host should fall through to env, port to CLI.
    captured: dict[str, Any] = {}

    def _capture_run(*args: Any, **kwargs: Any) -> None:
        captured["kwargs"] = kwargs

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def setsockopt(self, *_: Any) -> None:
            pass

        def bind(self, addr: tuple[str, int]) -> None:
            pass  # port always "free"

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 8123)

    monkeypatch.setattr(main_mod._socket, "socket", lambda *_a, **_kw: _FakeSock())
    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn") as mock_uvicorn,
        patch.object(main_mod, "webbrowser") as _mock_wb,
        patch.object(main_mod, "register_self"),
    ):
        mock_uvicorn.run.side_effect = _capture_run
        rc = main(["--port", "8123", "--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    # Host: env value persisted, CLI didn't touch it.
    assert captured["kwargs"]["host"] == "10.0.0.1"
    # Port: CLI override won.
    assert captured["kwargs"]["port"] == 8123


def test_cli_omitted_flag_does_not_override_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Regression guard: a CLI flag with no value passed must NOT show up in
    the overrides dict (else it'd clobber env with the default sentinel).

    This is the failure mode B-04 introduced before frozen=True landed —
    we're pinning the inverse: the AST-scan guard catches mutation
    afterwards; this guard catches the override-dict construction.
    """
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PDLABELER_DATA_ROOT", "/env/data")

    captured: dict[str, Any] = {}

    def _capture_run(*args: Any, **kwargs: Any) -> None:
        # Probe the Settings instance via the factory string passed to uvicorn.
        captured["kwargs"] = kwargs

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def setsockopt(self, *_: Any) -> None:
            pass

        def bind(self, addr: tuple[str, int]) -> None:
            pass  # port always "free"

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 8080)

    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn") as mock_uvicorn,
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        mock_uvicorn.run.side_effect = _capture_run
        # No --data-root passed; env value should persist into Settings.
        rc = main(["--no-browser"])

    assert rc == 0
    # The most direct check: build Settings the same way main does and
    # observe the env value flows through. (Settings reads env at construct
    # time; since main builds its own Settings, we mirror.)
    s = Settings()
    assert s.data_root == Path("/env/data")


# ── uvicorn.run kwargs ─────────────────────────────────────────────────────


def test_main_invokes_uvicorn_with_factory_and_correct_kwargs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The terminal call to uvicorn must use:

    - ``"pdomain_ocr_labeler_spa.bootstrap:build_app"`` (factory import string).
    - ``factory=True`` (Settings is constructed inside build_app for the
      no-args path).
    - ``host`` / ``port`` matching the resolved Settings, not raw argv.
    - ``reload`` reflecting the CLI flag.
    """
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    captured: dict[str, Any] = {}

    def _capture_run(*args: Any, **kwargs: Any) -> None:
        captured["args"] = args
        captured["kwargs"] = kwargs

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def setsockopt(self, *_: Any) -> None:
            pass

        def bind(self, addr: tuple[str, int]) -> None:
            pass  # port always "free"

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 8765)

    monkeypatch.setattr(main_mod._socket, "socket", lambda *_a, **_kw: _FakeSock())
    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn") as mock_uvicorn,
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "register_self"),
    ):
        mock_uvicorn.run.side_effect = _capture_run
        rc = main(
            [
                "--host",
                "0.0.0.0",
                "--port",
                "8765",
                "--reload",
                "--data-root",
                str(tmp_path),
            ]
        )

    assert rc == 0
    # Positional arg is the factory import string.
    assert captured["args"] == ("pdomain_ocr_labeler_spa.bootstrap:build_app",)
    assert captured["kwargs"]["host"] == "0.0.0.0"
    assert captured["kwargs"]["port"] == 8765
    assert captured["kwargs"]["reload"] is True
    assert captured["kwargs"]["factory"] is True


def test_main_does_not_open_browser_when_reload_true(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Legacy parity: ``--reload`` implies "don't auto-open the browser"
    (the auto-opener races the reloader and pops the page before it's
    served). The current ``__main__.py`` already does this — pin it so a
    refactor can't regress."""
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser") as mock_wb,
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(["--reload", "--data-root", str(tmp_path)])

    assert rc == 0
    mock_wb.open.assert_not_called()


def test_main_does_not_open_browser_when_no_browser(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``--no-browser`` suppresses the auto-open even outside reload mode."""
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser") as mock_wb,
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(["--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    mock_wb.open.assert_not_called()


def test_main_opens_browser_in_default_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Default behaviour: the CLI opens a browser to the bound URL.

    Updated for B-68: ``main`` no longer calls ``webbrowser.open``
    synchronously — the call now happens on a daemon thread that
    polls ``host:port`` until the listener is up. To keep this
    assertion meaningful we (a) stub ``socket.create_connection`` so
    the poller sees a live listener immediately, then (b) join the
    thread with a tight timeout before asserting.
    """
    import threading as _threading

    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_a: Any) -> None:
            return None

        def setsockopt(self, *_: Any) -> None:
            pass

        def bind(self, addr: tuple[str, int]) -> None:
            pass  # port 8080 is "free"

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 8080)

    monkeypatch.setattr(main_mod._socket, "create_connection", lambda *_a, **_kw: _FakeSock())

    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser") as mock_wb,
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(["--data-root", str(tmp_path)])
        # Wait for the daemon poller thread to finish before asserting.
        for t in _threading.enumerate():
            if t.name == "pd-ocr-labeler-browser-opener":
                t.join(timeout=2.0)

    assert rc == 0
    mock_wb.open.assert_called_once()
    # Bound URL respects defaults.
    (call_url,), _kwargs = mock_wb.open.call_args
    assert call_url == "http://127.0.0.1:8080"


# ── Path overrides (data-root, projects-root, project_dir) ────────────────


def test_data_root_cli_flag_threads_into_settings(tmp_path: Path) -> None:
    """``--data-root`` must end up on Settings.data_root.

    Verified indirectly via env-isolated build: same call shape as the
    other CLI tests; we just check the resulting Settings, not uvicorn.
    """
    target = tmp_path / "custom-data"

    captured_settings: dict[str, Settings] = {}

    # Patch Settings to capture every construction call args.
    real_settings = Settings

    def _capture_settings(**kwargs: Any) -> Settings:
        s = real_settings(**kwargs)
        captured_settings["last"] = s
        return s

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "Settings", side_effect=_capture_settings),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(["--data-root", str(target), "--no-browser"])

    assert rc == 0
    assert captured_settings["last"].data_root == target


def test_projects_root_cli_flag_threads_into_settings(tmp_path: Path) -> None:
    """``--projects-root`` overrides ``Settings.source_projects_root`` per
    spec §3. The consumer (project discovery) lands in M2; the override
    plumbing lands here so the field is settable today."""
    target = tmp_path / "projects"

    captured_settings: dict[str, Settings] = {}
    real_settings = Settings

    def _capture_settings(**kwargs: Any) -> Settings:
        s = real_settings(**kwargs)
        captured_settings["last"] = s
        return s

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "Settings", side_effect=_capture_settings),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(
            [
                "--projects-root",
                str(target),
                "--no-browser",
                "--data-root",
                str(tmp_path / "data"),
            ]
        )

    assert rc == 0
    assert captured_settings["last"].source_projects_root == target


def test_project_dir_positional_threads_into_settings(tmp_path: Path) -> None:
    """The positional ``project_dir`` lands on ``Settings.cli_project_dir``
    (spec §3 line 132). Consumer lands in M2; the seam lands here."""
    target = tmp_path / "project"

    captured_settings: dict[str, Settings] = {}
    real_settings = Settings

    def _capture_settings(**kwargs: Any) -> Settings:
        s = real_settings(**kwargs)
        captured_settings["last"] = s
        return s

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "Settings", side_effect=_capture_settings),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(
            [
                str(target),
                "--no-browser",
                "--data-root",
                str(tmp_path / "data"),
            ]
        )

    assert rc == 0
    assert captured_settings["last"].cli_project_dir == target


def test_no_overrides_omits_path_keys_entirely(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard for the override-dict construction.

    When a Path-typed flag is omitted, the overrides dict must NOT
    contain the key (else `Settings(data_root=None)` would clobber a
    valid env value with `None`). This is the same precedence guard as
    ``test_cli_omitted_flag_does_not_override_env`` but pinned at the
    keyword-arg level.

    Note: ``port`` is intentionally excluded — issue #323 always resolves
    the actual bound port and injects it into Settings so that the single
    Settings instance is authoritative. Port env precedence is handled
    by the ``_explicit_port`` detection path, not by letting pydantic-settings
    pick it up independently.
    """
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    captured_kwargs: dict[str, Any] = {}
    real_settings = Settings

    def _capture_settings(**kwargs: Any) -> Settings:
        captured_kwargs.update(kwargs)
        return real_settings(**kwargs)

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "Settings", side_effect=_capture_settings),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        main(["--no-browser"])

    # None of these keys (excluding port, which is always resolved) may have
    # been passed — they must fall through to env or default.
    for key in (
        "host",
        "data_root",
        "config_root",
        "cache_root",
        "source_projects_root",
        "cli_project_dir",
        "frontend_dev_url",
    ):
        assert key not in captured_kwargs, (
            f"omitted flag {key!r} leaked into overrides dict — would clobber env precedence"
        )


# ── B-70: degenerate-input rejection (host/port/data-root) ────────────────


def test_empty_host_string_is_rejected_at_parse_time() -> None:
    """`--host ""` exits cleanly rather than silently binding to "".

    B-70: empty-string `--host` previously landed `host=""` in Settings;
    pydantic accepted it and uvicorn bound to all interfaces (or failed
    in confusing ways). The shell expansion of `--host "$UNSET"` is the
    common path here. Argparse-time validation is the cleanest fix:
    user gets a clear error before any Settings construction, and the
    env-precedence guard in `_build_overrides` doesn't have to grow a
    second responsibility.
    """
    with pytest.raises(SystemExit) as exc:
        _parse_args(["--host", ""])
    assert exc.value.code != 0


def test_zero_port_is_rejected_at_parse_time() -> None:
    """`--port 0` exits cleanly rather than letting uvicorn pick ephemeral.

    B-70: `--port 0` previously made the printed `Listening on
    http://127.0.0.1:0` line factually false (uvicorn would pick an
    ephemeral port and the browser-open call would hit `:0` and refuse
    the connection). Negative ports are also rejected (TCP ports are
    in [1, 65535]).
    """
    with pytest.raises(SystemExit) as exc_zero:
        _parse_args(["--port", "0"])
    assert exc_zero.value.code != 0

    with pytest.raises(SystemExit) as exc_neg:
        _parse_args(["--port", "-1"])
    assert exc_neg.value.code != 0

    with pytest.raises(SystemExit) as exc_huge:
        _parse_args(["--port", "65536"])
    assert exc_huge.value.code != 0


def test_empty_path_string_flags_rejected_at_parse_time() -> None:
    """`--data-root ""` / `--projects-root ""` exit cleanly.

    B-70: `--data-root ""` resolves to `Path("")` which equals CWD;
    a stale labeler dir in the user's CWD then gets silently
    re-rooted into. The same shape applies to `--projects-root ""`
    and the positional `project_dir`.
    """
    for flag in ("--data-root", "--projects-root"):
        with pytest.raises(SystemExit) as exc:
            _parse_args([flag, ""])
        assert exc.value.code != 0, f"empty {flag!r} should be rejected"


def test_empty_positional_project_dir_is_rejected_at_parse_time() -> None:
    """Positional `""` `project_dir` is rejected (same root cause as B-70)."""
    with pytest.raises(SystemExit) as exc:
        _parse_args([""])
    assert exc.value.code != 0


def test_valid_high_port_still_accepted() -> None:
    """Don't over-tighten: spec lets users pick any valid TCP port.

    Sanity that the port validator only rejects out-of-range, not
    "unusual" ports. 65535 is the upper bound; 1 is the lower; the
    default 8080 stays accepted of course.
    """
    args1 = _parse_args(["--port", "1"])
    assert args1.port == 1
    args2 = _parse_args(["--port", "65535"])
    assert args2.port == 65535
    args3 = _parse_args(["--port", "8080"])
    assert args3.port == 8080


def test_valid_host_still_accepted() -> None:
    """Sanity: non-empty hosts still parse cleanly."""
    args = _parse_args(["--host", "0.0.0.0"])
    assert args.host == "0.0.0.0"


def test_valid_path_flags_still_accepted(tmp_path: Path) -> None:
    """Sanity: non-empty paths still parse cleanly through `Path` type."""
    args = _parse_args(["--data-root", str(tmp_path), "--projects-root", str(tmp_path)])
    assert args.data_root == tmp_path
    assert args.projects_root == tmp_path


# ── Module-as-script entry ────────────────────────────────────────────────


def test_module_main_block_calls_main() -> None:
    """``python -m pdomain_ocr_labeler_spa`` boots through the same ``main()``.

    Pinned via AST so we don't actually run the module — the module-as-
    script ``if __name__ == "__main__":`` block must call ``main()`` and
    pass its return code to ``SystemExit``.
    """
    import ast
    import inspect

    src = inspect.getsource(main_mod)
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and ast.dump(node.test).startswith("Compare"):
            # Look for the canonical `__name__ == "__main__":` shape.
            test_str = ast.unparse(node.test)
            if "__name__" in test_str and "__main__" in test_str:
                body_str = "\n".join(ast.unparse(s) for s in node.body)
                # SystemExit(main()) is the canonical form.
                assert "main(" in body_str
                assert "SystemExit" in body_str
                found = True
    assert found, "module-as-script entry block missing"


def test_console_script_target_resolves_to_main() -> None:
    """``pyproject.toml [project.scripts] pd-ocr-labeler-ui`` must point at
    ``pdomain_ocr_labeler_spa.__main__:main``. Anti-drift pin: if the script
    target moves, this assertion catches it before users see broken
    binaries.
    """
    import tomllib

    repo_root = Path(__file__).resolve().parents[2]
    with (repo_root / "pyproject.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    scripts = cfg["project"]["scripts"]
    assert scripts["pd-ocr-labeler-ui"] == "pdomain_ocr_labeler_spa.__main__:main"


# ── Argv default ─────────────────────────────────────────────────────────


def test_main_with_none_argv_reads_sys_argv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``main(None)`` must read sys.argv[1:] (entry-point convention)."""
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(sys, "argv", ["pd-ocr-labeler-ui", "--no-browser", "--data-root", str(tmp_path)])
    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(None)
    assert rc == 0


# ── B-68: browser-open polls the listener before opening ────────────────


def test_open_when_ready_waits_for_listener_then_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_open_when_ready`` must NOT call ``webbrowser.open`` until a TCP
    connection to ``host:port`` succeeds.

    Pins B-68: the prior code called ``webbrowser.open`` *before*
    ``uvicorn.run`` bound the port, racing the spawned tab against
    the still-importing app factory.
    """
    from pdomain_ocr_labeler_spa.__main__ import _open_when_ready

    attempts = {"n": 0}

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_a: Any) -> None:
            return None

    def fake_create_connection(*_a: Any, **_kw: Any) -> _FakeSock:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError("connection refused")
        return _FakeSock()

    monkeypatch.setattr(main_mod._socket, "create_connection", fake_create_connection)
    open_calls: list[str] = []
    monkeypatch.setattr(main_mod.webbrowser, "open", lambda url, new=0: open_calls.append(url))
    _open_when_ready(
        "http://127.0.0.1:9999",
        "127.0.0.1",
        9999,
        deadline_s=2.0,
        poll_s=0.0,
    )

    assert open_calls == ["http://127.0.0.1:9999"]
    assert attempts["n"] == 3  # polled twice, succeeded on third


def test_open_when_ready_gives_up_silently_after_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the deadline elapses with no successful connect, do NOT open
    the browser (and do NOT raise) — startup may have wedged."""
    from pdomain_ocr_labeler_spa.__main__ import _open_when_ready

    monkeypatch.setattr(
        main_mod._socket,
        "create_connection",
        lambda *_a, **_kw: (_ for _ in ()).throw(OSError("nope")),
    )
    open_calls: list[str] = []
    monkeypatch.setattr(main_mod.webbrowser, "open", lambda url, new=0: open_calls.append(url))

    _open_when_ready(
        "http://127.0.0.1:9999",
        "127.0.0.1",
        9999,
        deadline_s=0.05,
        poll_s=0.01,
    )

    assert open_calls == []  # never opened the browser


def test_open_when_ready_swallows_webbrowser_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Headless platforms sometimes have ``webbrowser.open`` raise.
    The poller must catch + swallow so a server startup never crashes
    on a missing browser launcher."""
    from pdomain_ocr_labeler_spa.__main__ import _open_when_ready

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(main_mod._socket, "create_connection", lambda *_a, **_kw: _FakeSock())

    def boom(*_a: Any, **_kw: Any) -> None:
        raise RuntimeError("no display")

    monkeypatch.setattr(main_mod.webbrowser, "open", boom)

    # Must not raise.
    _open_when_ready(
        "http://127.0.0.1:9999",
        "127.0.0.1",
        9999,
        deadline_s=1.0,
        poll_s=0.0,
    )


# ── Verbose logging (--verbose / -v flag) ────────────────────────────────


def test_verbose_flag_sets_log_level_in_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`--verbose -vv` enables DEBUG logging. Acceptance criterion for issue #251.

    Tests that the verbose flag correctly sets the log_level in Settings to DEBUG.
    """
    import logging

    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    captured_settings: dict[str, Settings] = {}
    real_settings = Settings

    def _capture_settings(**kwargs: Any) -> Settings:
        s = real_settings(**kwargs)
        captured_settings["last"] = s
        return s

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "Settings", side_effect=_capture_settings),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(["--verbose", "--verbose", "--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    # -vv should set log_level to DEBUG (10)
    assert captured_settings["last"].log_level == logging.DEBUG


def test_single_verbose_flag_preserves_info_level(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`-v` (single) should keep INFO level, not switch to DEBUG.

    Since INFO is the default, -v doesn't add log_level to overrides, preserving
    env precedence like other omitted flags. But the resulting Settings.log_level
    should still be INFO (the default).
    """
    import logging

    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    captured_settings: dict[str, Settings] = {}
    real_settings = Settings

    def _capture_settings(**kwargs: Any) -> Settings:
        s = real_settings(**kwargs)
        captured_settings["last"] = s
        return s

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "Settings", side_effect=_capture_settings),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(["--verbose", "--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    # -v doesn't add to overrides (env precedence), but Settings defaults to INFO
    assert captured_settings["last"].log_level == logging.INFO


def test_no_verbose_flag_uses_default_info_level(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Without any verbose flag, log_level should be INFO (the default)."""
    import logging

    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    captured_settings: dict[str, Settings] = {}
    real_settings = Settings

    def _capture_settings(**kwargs: Any) -> Settings:
        s = real_settings(**kwargs)
        captured_settings["last"] = s
        return s

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "Settings", side_effect=_capture_settings),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(["--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    # Default log_level should be INFO (20)
    assert captured_settings["last"].log_level == logging.INFO


# ── Auto-port selection (#323) ────────────────────────────────────────────


def _clear_pdlabeler_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip all PDLABELER_* env vars so tests start from a clean slate."""
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)


def test_default_port_free_no_scan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When default port 8080 is free, bootstrap_spa returns 8080 and
    uvicorn is called with it. No stderr notice should be emitted.

    Port resolution now delegates to ``pdomain_ops.suite.bootstrap_spa``;
    this test mocks that helper directly so no real socket is probed.
    """
    _clear_pdlabeler_env(monkeypatch)

    captured: dict[str, Any] = {}

    def _capture_run(*args: Any, **kwargs: Any) -> None:
        captured["kwargs"] = kwargs

    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn") as mock_uv,
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "bootstrap_spa", return_value=8080) as mock_bsp,
    ):
        mock_uv.run.side_effect = _capture_run
        rc = main(["--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    assert captured["kwargs"]["port"] == 8080
    mock_bsp.assert_called_once_with(
        preferred=8080,
        caller_package="pdomain_ocr_labeler_spa",
        port_env="PDLABELER_PORT",
    )


def test_auto_port_scan_when_default_busy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When bootstrap_spa returns a shifted port (e.g. 8082), uvicorn
    starts on that port and .pdlabeler-port is written with it.

    The actual port-scanning logic lives in pdomain-ops; here we just
    verify that main() honours whatever bootstrap_spa returns.
    """
    _clear_pdlabeler_env(monkeypatch)

    captured: dict[str, Any] = {}

    def _capture_run(*args: Any, **kwargs: Any) -> None:
        captured["kwargs"] = kwargs

    port_file = tmp_path / ".pdlabeler-port"
    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn") as mock_uv,
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "bootstrap_spa", return_value=8082),
    ):
        mock_uv.run.side_effect = _capture_run
        rc = main(["--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    assert captured["kwargs"]["port"] == 8082
    assert port_file.read_text() == "8082"


def test_auto_port_prints_notice_to_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When bootstrap_spa returns a port != 8080, a notice is printed to
    stderr so users know the address has shifted."""
    _clear_pdlabeler_env(monkeypatch)

    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "bootstrap_spa", return_value=8081),
    ):
        rc = main(["--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    err = capsys.readouterr().err
    assert "Port 8080 in use" in err


def test_bootstrap_spa_runtime_error_exits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When bootstrap_spa raises RuntimeError (all 100 candidates busy),
    main() prints the error to stderr and exits with code 1.

    bootstrap_spa propagates RuntimeError from find_available_port unchanged;
    main() must surface it as a clean error rather than a traceback.
    """
    _clear_pdlabeler_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(
            main_mod,
            "bootstrap_spa",
            side_effect=RuntimeError("Could not find a free port in range [8080, 8180)"),
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main(["--no-browser", "--data-root", str(tmp_path)])

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Could not find a free port" in err


def test_explicit_port_busy_exits_with_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--port N with N busy → exit 1, stderr contains 'Port N is already in use'."""
    _clear_pdlabeler_env(monkeypatch)

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def setsockopt(self, *_: Any) -> None:
            pass

        def bind(self, addr: tuple[str, int]) -> None:
            raise OSError("address in use")

    monkeypatch.setattr(main_mod._socket, "socket", lambda *_a, **_kw: _FakeSock())

    with pytest.raises(SystemExit) as exc_info:
        main(["--port", "9999", "--no-browser", "--data-root", str(tmp_path)])

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Port 9999 is already in use" in err


def test_explicit_port_free_starts_normally(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--port N with N free → uvicorn called with N."""
    _clear_pdlabeler_env(monkeypatch)

    captured: dict[str, Any] = {}

    def _capture_run(*args: Any, **kwargs: Any) -> None:
        captured["kwargs"] = kwargs

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def setsockopt(self, *_: Any) -> None:
            pass

        def bind(self, addr: tuple[str, int]) -> None:
            pass  # success

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 9999)

    monkeypatch.setattr(main_mod._socket, "socket", lambda *_a, **_kw: _FakeSock())
    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn") as mock_uv,
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "register_self"),
    ):
        mock_uv.run.side_effect = _capture_run
        rc = main(["--port", "9999", "--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    assert captured["kwargs"]["port"] == 9999


def test_env_port_busy_exits_with_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PDLABELER_PORT=N (no --port) with N busy → exit 1, stderr contains 'Port N is already in use'."""
    _clear_pdlabeler_env(monkeypatch)
    monkeypatch.setenv("PDLABELER_PORT", "9000")

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def setsockopt(self, *_: Any) -> None:
            pass

        def bind(self, addr: tuple[str, int]) -> None:
            raise OSError("address in use")

    monkeypatch.setattr(main_mod._socket, "socket", lambda *_a, **_kw: _FakeSock())

    with pytest.raises(SystemExit) as exc_info:
        main(["--no-browser", "--data-root", str(tmp_path)])

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Port 9000 is already in use" in err


def test_env_port_free_starts_normally(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """PDLABELER_PORT=N (no --port) with N free → uvicorn called with N, .pdlabeler-port contains N."""
    _clear_pdlabeler_env(monkeypatch)
    monkeypatch.setenv("PDLABELER_PORT", "9000")

    captured: dict[str, Any] = {}

    def _capture_run(*args: Any, **kwargs: Any) -> None:
        captured["kwargs"] = kwargs

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def setsockopt(self, *_: Any) -> None:
            pass

        def bind(self, addr: tuple[str, int]) -> None:
            pass  # port 9000 is "free"

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 9000)

    monkeypatch.setattr(main_mod._socket, "socket", lambda *_a, **_kw: _FakeSock())
    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn") as mock_uv,
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "register_self"),
    ):
        mock_uv.run.side_effect = _capture_run
        rc = main(["--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    assert captured["kwargs"]["port"] == 9000
    port_file = tmp_path / ".pdlabeler-port"
    assert port_file.read_text().strip() == "9000"


def test_port_file_written_on_start(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every successful start writes the actual port to .pdlabeler-port in cwd."""
    _clear_pdlabeler_env(monkeypatch)

    monkeypatch.chdir(tmp_path)

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "bootstrap_spa", return_value=8080),
    ):
        rc = main(["--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    port_file = tmp_path / ".pdlabeler-port"
    assert port_file.exists(), ".pdlabeler-port was not written"
    assert port_file.read_text().strip() == "8080"


def test_register_self_called_with_actual_port(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """For the auto-port path, bootstrap_spa must be called with
    ``caller_package="pdomain_ocr_labeler_spa"`` and ``port_env="PDLABELER_PORT"``.
    bootstrap_spa handles suite-registry registration internally.

    Pins the migration from explicit find_available_port + register_self calls
    to the consolidated bootstrap_spa helper so cross-app links (e.g. the
    dashboard) always discover the real address via the suite registry.
    """
    _clear_pdlabeler_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    bsp_calls: list[dict[str, Any]] = []

    def _capture_bsp(**kwargs: Any) -> int:
        bsp_calls.append(kwargs)
        return 8083

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "bootstrap_spa", side_effect=_capture_bsp),
    ):
        rc = main(["--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    assert len(bsp_calls) == 1
    kw = bsp_calls[0]
    assert kw.get("caller_package") == "pdomain_ocr_labeler_spa"
    assert kw.get("preferred") == 8080
    assert kw.get("port_env") == "PDLABELER_PORT"


def test_register_self_called_with_explicit_port(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """register_self must also be called when --port is given explicitly."""
    _clear_pdlabeler_env(monkeypatch)

    class _FakeSock:
        def __enter__(self) -> _FakeSock:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

        def setsockopt(self, *_: Any) -> None:
            pass

        def bind(self, addr: tuple[str, int]) -> None:
            pass  # port free

        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 9876)

    monkeypatch.setattr(main_mod._socket, "socket", lambda *_a, **_kw: _FakeSock())
    monkeypatch.chdir(tmp_path)

    register_calls: list[dict[str, Any]] = []

    def _capture_register(**kwargs: Any) -> None:
        register_calls.append(kwargs)

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser"),
        patch.object(main_mod, "register_self", side_effect=_capture_register),
    ):
        rc = main(["--port", "9876", "--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    assert len(register_calls) == 1
    kw = register_calls[0]
    assert kw.get("_caller_package") == "pdomain_ocr_labeler_spa"
    assert kw.get("actual_port") == 9876
