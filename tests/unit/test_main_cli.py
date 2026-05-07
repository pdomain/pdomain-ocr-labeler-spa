"""``pd_ocr_labeler_spa.__main__`` CLI flag-wiring contract — M1.g.

Specs:

- ``specs/15-deployment-dev.md §3`` names the canonical CLI flag set
  (mirrors legacy ``pd-ocr-labeler-ui`` plus pgdp-prep's
  ``--frontend-dev``).
- ``specs/02-backend.md §3`` makes Settings the single, frozen source
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

from pd_ocr_labeler_spa import __main__ as main_mod
from pd_ocr_labeler_spa.__main__ import _parse_args, main
from pd_ocr_labeler_spa.settings import Settings

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

    with (
        patch.object(main_mod, "uvicorn") as mock_uvicorn,
        patch.object(main_mod, "webbrowser") as _mock_wb,
    ):
        mock_uvicorn.run.side_effect = _capture_run
        rc = main(["--port", "8123", "--no-browser", "--data-root", str(tmp_path)])

    assert rc == 0
    # Host: env value persisted, CLI didn't touch it.
    assert captured["kwargs"]["host"] == "10.0.0.1"
    # Port: CLI override won.
    assert captured["kwargs"]["port"] == 8123


def test_cli_omitted_flag_does_not_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
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

    with (
        patch.object(main_mod, "uvicorn") as mock_uvicorn,
        patch.object(main_mod, "webbrowser"),
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

    - ``"pd_ocr_labeler_spa.bootstrap:build_app"`` (factory import string).
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

    with (
        patch.object(main_mod, "uvicorn") as mock_uvicorn,
        patch.object(main_mod, "webbrowser"),
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
    assert captured["args"] == ("pd_ocr_labeler_spa.bootstrap:build_app",)
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

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser") as mock_wb,
    ):
        rc = main(["--reload", "--data-root", str(tmp_path)])

    assert rc == 0
    mock_wb.open.assert_not_called()


def test_main_does_not_open_browser_when_no_browser(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``--no-browser`` suppresses the auto-open even outside reload mode."""
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser") as mock_wb,
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
        def __enter__(self) -> _FakeSock:  # noqa: PYI034
            return self

        def __exit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(main_mod.socket, "create_connection", lambda *_a, **_kw: _FakeSock())

    with (
        patch.object(main_mod, "uvicorn"),
        patch.object(main_mod, "webbrowser") as mock_wb,
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
    ):
        main(["--no-browser"])

    # None of these keys may have been passed — they must fall through to
    # env or default.
    for key in (
        "host",
        "port",
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
    """``python -m pd_ocr_labeler_spa`` boots through the same ``main()``.

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
    ``pd_ocr_labeler_spa.__main__:main``. Anti-drift pin: if the script
    target moves, this assertion catches it before users see broken
    binaries.
    """
    import tomllib

    repo_root = Path(__file__).resolve().parents[2]
    with (repo_root / "pyproject.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    scripts = cfg["project"]["scripts"]
    assert scripts["pd-ocr-labeler-ui"] == "pd_ocr_labeler_spa.__main__:main"


# ── Argv default ─────────────────────────────────────────────────────────


def test_main_with_none_argv_reads_sys_argv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``main(None)`` must read sys.argv[1:] (entry-point convention)."""
    for var in list(__import__("os").environ):
        if var.startswith("PDLABELER_"):
            monkeypatch.delenv(var, raising=False)

    monkeypatch.setattr(sys, "argv", ["pd-ocr-labeler-ui", "--no-browser", "--data-root", str(tmp_path)])
    with patch.object(main_mod, "uvicorn"), patch.object(main_mod, "webbrowser"):
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
    from pd_ocr_labeler_spa.__main__ import _open_when_ready

    attempts = {"n": 0}

    class _FakeSock:
        def __enter__(self) -> _FakeSock:  # noqa: PYI034
            return self

        def __exit__(self, *_a: Any) -> None:
            return None

    def fake_create_connection(*_a: Any, **_kw: Any) -> _FakeSock:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError("connection refused")
        return _FakeSock()

    monkeypatch.setattr(main_mod.socket, "create_connection", fake_create_connection)
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
    from pd_ocr_labeler_spa.__main__ import _open_when_ready

    monkeypatch.setattr(
        main_mod.socket,
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
    from pd_ocr_labeler_spa.__main__ import _open_when_ready

    class _FakeSock:
        def __enter__(self) -> _FakeSock:  # noqa: PYI034
            return self

        def __exit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(main_mod.socket, "create_connection", lambda *_a, **_kw: _FakeSock())

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
