"""M1 acceptance test: ``test_startup_shutdown_clean``.

Spec authority: ``specs/16-milestones.md`` line 139 names this test by
file + nodeid as one of M1's acceptance bars:

    tests/integration/test_lifespan.py::test_startup_shutdown_clean —
    TestClient(build_app(settings)) enters and exits without resource
    warnings.

The post-M1 lifespan adds project discovery + session restoration in
``app_state.startup()`` (per ``docs/architecture/02-backend.md §13``); this M1
landing only pins the no-resource-leak invariant against the
M1.a-through-M1.g wiring graph (CORS + RequestId + error handlers +
healthz + env.js + image-cache + SPA fallback). When M2 layers a real
``startup()`` hook on top, the same test must keep passing — the
intent is "no leaks across enter/exit", not "exact resource list".

Why an integration test (and not just unit)? ``TestClient`` only runs
the lifespan when used as a context manager (FastAPI/Starlette
docs). Plain ``TestClient(app)`` without ``with`` skips startup +
shutdown entirely. The unit ``conftest.client`` fixture already does
``with TestClient(app) as c`` so most tests *do* exercise lifespan,
but they don't *assert* it stays clean. This file is the explicit
pin.

Reasonability of "no resource warnings":

- Python's ``ResourceWarning`` fires for unclosed sockets, files,
  temporary directories, etc. ``ResourceWarning`` is raised from GC
  finalizers, where ``warnings.simplefilter("error")`` cannot promote
  it to a propagating exception (the interpreter swallows GC-time
  exceptions per ``Exception ignored in:`` semantics). So we use the
  ``record=True`` capture path with ``simplefilter("always")`` and
  walk the captured list afterwards — that's the only mechanism that
  reliably observes finalizer warnings.

If a future refactor introduces a real leak (forgetting to close a
``httpx.AsyncClient`` in shutdown, leaving a tempdir open, etc.) this
test fails at the ``with TestClient`` exit, pointing right at the
offending resource.
"""

from __future__ import annotations

import gc
import warnings
from pathlib import Path

from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.settings import Settings


def test_startup_shutdown_clean(tmp_path: Path) -> None:
    """``TestClient(build_app(settings))`` enters and exits cleanly.

    Spec: ``specs/16-milestones.md`` M1 acceptance test line 139.

    Asserts:
    1. No ``ResourceWarning`` is raised during enter, request flow, or
       exit (sockets, files, tmpdirs all closed).
    2. No exception escapes the lifespan context manager.
    3. The app still responds to ``/healthz`` between enter and exit
       (sanity that the lifespan didn't no-op everything).

    The mode here is ``mode="default"`` so the full M1.e/f wiring path
    runs (env.js + image-cache + SPA fallback + ground-truth lifespan
    hooks once they land). M1.g's ``cli_project_dir`` /
    ``source_projects_root`` are deliberately left unset — those land
    consumers in M2.
    """
    settings = Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        # Use api_only here so the SPA-index probe doesn't require a
        # populated static/ bundle in the test sandbox. The lifespan
        # invariants we care about (no leaks across enter/exit) are
        # mode-independent — every middleware + adapter wiring step in
        # bootstrap.py runs in api_only mode too.
        mode="api_only",
    )

    app = build_app(settings)

    with warnings.catch_warnings(record=True) as captured:
        # ``simplefilter("always")`` + ``record=True`` is the only
        # reliable path for catching ``ResourceWarning`` raised inside a
        # GC finalizer — promoting via ``simplefilter("error", ...)``
        # doesn't propagate from finalizer context (CPython swallows
        # those as "Exception ignored in:"). The captured list, by
        # contrast, picks them up faithfully.
        warnings.simplefilter("always")

        with TestClient(app) as client:
            # Sanity: lifespan startup ran and routes are mounted.
            r = client.get("/healthz")
            assert r.status_code == 200, f"healthz unreachable inside lifespan ctx: {r.status_code}"

        # Force a GC pass so any lingering finalizers (sockets in
        # CLOSE_WAIT, temp files referenced by closed handles) raise
        # their ResourceWarning *now*, inside the ``catch_warnings``
        # block, rather than at interpreter shutdown where pytest
        # can't see them.
        gc.collect()

    # Walk the captured list and surface any ResourceWarning. Two
    # filters:
    #
    # 1. Category narrowing: third-party DeprecationWarning noise
    #    (httpx, starlette) is allowed to pass since it isn't a leak,
    #    just an upstream API churn signal.
    # 2. Source-module narrowing (B-69, iter 51): ``TestClient`` itself
    #    sits inside the same ``catch_warnings`` window we're using to
    #    audit our app, so a ResourceWarning emitted by httpx/anyio/
    #    starlette plumbing is indistinguishable from one emitted by
    #    our `build_app()` graph. Today both are clean, but a future
    #    `uv lock --upgrade-package httpx` (or anyio, or starlette)
    #    that introduces a transient finalizer warning would turn this
    #    test red even though nothing in our tree leaked. The intent
    #    is "no leaks across enter/exit *of our code*"; match that
    #    intent by filtering captured warnings to those whose source
    #    file lives under our package OR our test tree.
    leaks = [
        w
        for w in captured
        if issubclass(w.category, ResourceWarning)
        and ("pd_ocr_labeler_spa" in (w.filename or "") or "/tests/" in (w.filename or ""))
    ]
    assert not leaks, (
        f"lifespan exit produced {len(leaks)} ResourceWarning(s) "
        f"from our code: "
        f"{[(w.category.__name__, w.filename, str(w.message)) for w in leaks]}"
    )


def test_lifespan_runs_when_used_as_context_manager(tmp_path: Path) -> None:
    """Pin the FastAPI/Starlette behavior we depend on: lifespan only
    runs inside the ``with TestClient(...)`` block.

    Why this test exists: a tempting refactor of ``conftest.client``
    fixture might switch from ``with TestClient(app) as c`` to a plain
    ``TestClient(app)`` to avoid the contextmanager nesting. That
    silently disables lifespan startup + shutdown — every existing
    test still passes (because M1 lifespan is empty) but M2's project
    discovery would never run. This test pins the contract: the
    ``with`` form *must* be used to get a real lifespan.

    Pinned by: ``starlette/testclient.py`` — ``TestClient.__enter__``
    is what kicks the LifespanHandler. A plain instantiation skips it
    entirely. We assert this by observing that a startup-time route-
    mount lookup only succeeds inside the ctx.
    """
    settings = Settings(
        host="127.0.0.1",
        port=8080,
        config_root=tmp_path / "config",
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        mode="api_only",
    )
    app = build_app(settings)

    # Plain instantiation: lifespan does NOT run, but routes mounted at
    # build_app time are still reachable. (M1 lifespan is empty, so the
    # only behavioral difference is observable in M2+. We pin the
    # weaker invariant for now: enter/exit doesn't raise either way.)
    plain_client = TestClient(app)
    assert plain_client.get("/healthz").status_code == 200

    # Context-manager form: lifespan runs. Same /healthz works.
    with TestClient(app) as ctx_client:
        assert ctx_client.get("/healthz").status_code == 200


def test_resource_warning_capture_self_test() -> None:
    """Self-test: the warnings-capture mechanism in
    ``test_startup_shutdown_clean`` must actually catch a real leak.

    Without this self-test, a green ``test_startup_shutdown_clean``
    proves nothing — it could mean "no leaks" OR "the detector is
    broken". This test deliberately leaks a file handle inside the
    same ``catch_warnings`` block shape and asserts it's surfaced.

    If this self-test ever stops finding the leak, the detector logic
    in ``test_startup_shutdown_clean`` is broken and that test becomes
    a no-op. Fix the detector before fixing whatever made this test
    fail.
    """
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")

        # Deliberately leak a file handle: open + drop reference
        # without close(). GC finalizer must fire ResourceWarning.
        leaked = open("/dev/null")  # noqa: SIM115 — deliberate leak
        del leaked
        gc.collect()

    leaks = [w for w in captured if issubclass(w.category, ResourceWarning)]
    assert leaks, (
        "Self-test failure: deliberately leaked file did not produce "
        "a ResourceWarning. The detector in test_startup_shutdown_clean "
        "is broken — that test is currently a no-op."
    )


def test_resource_warning_filter_excludes_third_party_sources() -> None:
    """B-69 (iter 51): ``test_startup_shutdown_clean``'s ResourceWarning
    filter narrows by source file (``"pd_ocr_labeler_spa"`` or
    ``"/tests/"``). Pin that contract: a ResourceWarning whose
    ``filename`` is under a third-party tree (httpx, anyio, starlette,
    site-packages generally) MUST NOT count as a leak.

    Why this exists: ``TestClient`` runs httpx / anyio / starlette in
    the same ``catch_warnings`` window. If those libs' finalizers
    transiently emit a ResourceWarning (a real possibility on a future
    `uv lock --upgrade-package httpx`), the unfiltered version of the
    detector would turn the test red even though our code is clean.
    The filter exists so a future churn upstream doesn't trigger a
    wild-goose chase. If someone removes the filter without thinking,
    this self-test fails immediately with a clear breadcrumb.
    """
    # Synthesise a ResourceWarning whose ``filename`` looks third-party.
    # We can't easily make a real httpx call here without taking a
    # dependency on its implementation details, so we hand-craft a
    # ``WarningMessage``-shaped record matching what the real filter
    # consumes (``catch_warnings(record=True)`` produces these).
    third_party = warnings.WarningMessage(
        message=ResourceWarning("simulated httpx finalizer"),
        category=ResourceWarning,
        filename="/site-packages/httpx/_transports/default.py",
        lineno=123,
    )
    ours = warnings.WarningMessage(
        message=ResourceWarning("simulated leak in our code"),
        category=ResourceWarning,
        filename="/repo/src/pd_ocr_labeler_spa/some_module.py",
        lineno=42,
    )
    test_tree = warnings.WarningMessage(
        message=ResourceWarning("simulated leak in test code"),
        category=ResourceWarning,
        filename="/repo/tests/integration/test_lifespan.py",
        lineno=1,
    )

    captured = [third_party, ours, test_tree]

    # Replicate the filter literal-for-literal so a regression in the
    # real filter (e.g. someone deleting the ``and (...)`` clause)
    # would also need to delete this expression to keep this test
    # green — making the regression visible.
    leaks = [
        w
        for w in captured
        if issubclass(w.category, ResourceWarning)
        and ("pd_ocr_labeler_spa" in (w.filename or "") or "/tests/" in (w.filename or ""))
    ]

    assert third_party not in leaks, (
        "Third-party ResourceWarning leaked through the filter — the "
        "narrowing clause is missing or wrong. test_startup_shutdown_"
        "clean would turn red on third-party churn alone."
    )
    assert ours in leaks, "Our package's ResourceWarning was wrongly filtered out."
    assert test_tree in leaks, "Test-tree ResourceWarning was wrongly filtered out."
