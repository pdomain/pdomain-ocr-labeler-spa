"""Unit tests for ``core.project_state`` — the M2-slice-2 mutable carrier.

Slice 2 ships a tiny ``ProjectState`` carrier that tracks *which project
is currently active* — separate from the frozen ``AppState`` (whose
adapter graph is wired once at build time). The carrier ships:

- An empty default (no project open).
- ``set_active_project(path)`` that validates via slice 1's
  ``validate_project_dir`` and swaps the active snapshot under a lock.
- A frozen ``ActiveProject`` snapshot returned by ``snapshot()`` so
  callers can hand the value to consumers without risking mutation
  through the returned reference.
- A monotonically-increasing ``generation`` counter so future SSE /
  cache-invalidation code (M3+) can detect "the active project
  changed under me" without diffing paths.

Slice 2 deliberately STOPS at: project enumeration, lifespan wiring
(slice 3), and HTTP routes that change the active project (slice 4).

Spec authority:
- ``specs/02-backend.md §13`` — background discovery + restoration
  (``POST /api/projects/load`` ultimately sets ``current_project_id``).
- ``specs/00-overview.md`` "State model" §lines-179-201 — backend keeps
  a single ``AppState`` with a per-project ``ProjectState`` map; this
  slice ships the *active-pointer* carrier; the per-project
  ``ProjectState`` map (with loaded ``Project``, GT, page states) is
  M2 proper.

The carrier name ``ProjectState`` is reserved for the spec-proper
object (``core/project_state.py``, see ``specs/16-milestones.md`` M2
backend bullet 1); to avoid colliding with that future module, slice
2 lands the carrier at ``core/active_project.py`` with classes
``ActiveProject`` (frozen snapshot) + ``ActiveProjectCarrier``
(mutable holder). When the spec-proper ``ProjectState`` lands, it'll
own the same swap discipline but with richer fields; the *carrier*
contract documented here is the seam.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

from pd_ocr_labeler_spa.core.active_project import (
    ActiveProject,
    ActiveProjectCarrier,
    InvalidProjectDirError,
)

# ── default empty state ────────────────────────────────────────────────────


def test_empty_carrier_has_no_active_project() -> None:
    """A freshly constructed carrier has no project active."""
    carrier = ActiveProjectCarrier()
    assert carrier.snapshot() is None


def test_empty_carrier_generation_starts_at_zero() -> None:
    """Generation counter starts at 0 — increments only on successful swaps."""
    carrier = ActiveProjectCarrier()
    assert carrier.generation == 0


# ── set_active_project: happy path ─────────────────────────────────────────


def test_set_active_project_swaps_to_a_valid_dir(tmp_path: Path) -> None:
    """Valid path → carrier holds an ``ActiveProject`` snapshot."""
    carrier = ActiveProjectCarrier()
    snap = carrier.set_active_project(tmp_path)
    assert isinstance(snap, ActiveProject)
    assert snap.path == tmp_path.resolve()
    assert carrier.snapshot() == snap


def test_set_active_project_resolves_path(tmp_path: Path) -> None:
    """Path is ``Path.resolve()``-d so symlink / relative trivia is canonical.

    Mirrors slice 1's ``ResolvedInitialProject.path`` discipline so a
    consumer that compares ``carrier.snapshot().path`` against
    ``resolved.path`` doesn't get tripped up by ``./foo`` vs ``foo``.
    """
    sub = tmp_path / "proj"
    sub.mkdir()
    snap = ActiveProjectCarrier().set_active_project(Path(str(sub) + "/."))
    assert snap.path == sub.resolve()


def test_set_active_project_default_label_is_dirname(tmp_path: Path) -> None:
    """Default label = ``path.name`` (matches legacy "project ID = dir name")."""
    sub = tmp_path / "MyProject_001"
    sub.mkdir()
    snap = ActiveProjectCarrier().set_active_project(sub)
    assert snap.label == "MyProject_001"


def test_set_active_project_explicit_label_overrides(tmp_path: Path) -> None:
    """Caller can override the label (used by future load-by-pretty-name flows)."""
    snap = ActiveProjectCarrier().set_active_project(tmp_path, label="Override")
    assert snap.label == "Override"


def test_set_active_project_records_opened_at(tmp_path: Path) -> None:
    """``opened_at`` is set to a monotonic UTC datetime on each swap."""
    carrier = ActiveProjectCarrier()
    snap = carrier.set_active_project(tmp_path)
    assert snap.opened_at is not None
    # second swap must produce a non-decreasing opened_at
    other = tmp_path / "other"
    other.mkdir()
    snap2 = carrier.set_active_project(other)
    assert snap2.opened_at >= snap.opened_at


def test_set_active_project_increments_generation(tmp_path: Path) -> None:
    """Each successful swap bumps ``generation`` by 1.

    Future SSE code can compare a stale generation to the current one
    to detect "the active project changed under me" without diffing
    the path string.
    """
    carrier = ActiveProjectCarrier()
    assert carrier.generation == 0
    carrier.set_active_project(tmp_path)
    assert carrier.generation == 1
    other = tmp_path / "other"
    other.mkdir()
    carrier.set_active_project(other)
    assert carrier.generation == 2


def test_set_active_project_emits_structured_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Successful swap emits an INFO log with stable structured keys.

    Mirrors slice 1's logging discipline so the active-project lifecycle
    is testable without parsing message strings.
    """
    caplog.set_level(logging.INFO, logger="pd_ocr_labeler_spa.core.active_project")
    ActiveProjectCarrier().set_active_project(tmp_path)
    matching = [
        r for r in caplog.records if getattr(r, "active_project_path", None) == str(tmp_path.resolve())
    ]
    assert len(matching) == 1
    assert matching[0].levelno == logging.INFO
    # generation extra is also present on the log line
    assert getattr(matching[0], "active_project_generation", None) == 1


# ── set_active_project: invalid input ──────────────────────────────────────


def test_set_active_project_rejects_missing_path(tmp_path: Path) -> None:
    """Missing path → ``InvalidProjectDirError``; carrier untouched."""
    carrier = ActiveProjectCarrier()
    missing = tmp_path / "nope"
    with pytest.raises(InvalidProjectDirError):
        carrier.set_active_project(missing)
    assert carrier.snapshot() is None
    assert carrier.generation == 0


def test_set_active_project_rejects_regular_file(tmp_path: Path) -> None:
    """Path-to-regular-file → ``InvalidProjectDirError``; carrier untouched."""
    f = tmp_path / "file.txt"
    f.write_text("hi")
    carrier = ActiveProjectCarrier()
    with pytest.raises(InvalidProjectDirError):
        carrier.set_active_project(f)
    assert carrier.snapshot() is None


def test_set_active_project_invalid_does_not_clobber_prior(tmp_path: Path) -> None:
    """Failed swap leaves the prior active snapshot intact (no half-swap)."""
    a = tmp_path / "a"
    a.mkdir()
    carrier = ActiveProjectCarrier()
    first = carrier.set_active_project(a)
    assert carrier.generation == 1

    with pytest.raises(InvalidProjectDirError):
        carrier.set_active_project(tmp_path / "missing")

    # Snapshot AND generation untouched — the swap was atomic.
    assert carrier.snapshot() == first
    assert carrier.generation == 1


# ── snapshot is frozen / mutation-safe ─────────────────────────────────────


def test_snapshot_is_frozen_dataclass(tmp_path: Path) -> None:
    """``ActiveProject`` is frozen — mutating a returned snapshot raises.

    Hard-frozen contract mirrors slice 1's ``ResolvedInitialProject``
    and ``AppState``; consumers can't mutate carrier state by mutating
    a returned reference.

    ``dataclasses.FrozenInstanceError`` IS-A ``AttributeError`` (per
    the stdlib), so we pin against ``AttributeError`` rather than the
    blind ``Exception`` ruff B017 forbids.
    """
    snap = ActiveProjectCarrier().set_active_project(tmp_path)
    with pytest.raises(AttributeError):
        snap.path = tmp_path / "evil"  # type: ignore[misc]


def test_snapshot_does_not_share_reference_with_internal_state(tmp_path: Path) -> None:
    """``snapshot()`` returns the same frozen instance that ``set_active_project``
    returned — but because it's frozen, the carrier doesn't need to copy.

    Pin: identity == identity. If a future maintainer adds a mutable
    field, this test forces them to also add ``deepcopy`` semantics
    (or to keep the snapshot frozen-all-the-way-down).
    """
    carrier = ActiveProjectCarrier()
    a = carrier.set_active_project(tmp_path)
    b = carrier.snapshot()
    assert a is b


# ── thread safety ──────────────────────────────────────────────────────────


def test_concurrent_set_active_project_serializes_under_lock(tmp_path: Path) -> None:
    """Concurrent swaps must produce a generation == thread_count, not
    interleave to a smaller number.

    The carrier swaps under a ``threading.Lock`` so two threads racing
    to ``set_active_project`` both succeed but the generation counter
    is the source of truth for "how many swaps actually completed."
    A non-locked impl would race the read-modify-write on
    ``generation`` and end up with a smaller count.
    """
    n_threads = 16
    dirs = []
    for i in range(n_threads):
        d = tmp_path / f"p_{i}"
        d.mkdir()
        dirs.append(d)

    carrier = ActiveProjectCarrier()
    barrier = threading.Barrier(n_threads)
    errors: list[Exception] = []

    def worker(p: Path) -> None:
        try:
            barrier.wait()
            carrier.set_active_project(p)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(d,)) for d in dirs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert carrier.generation == n_threads
    snap = carrier.snapshot()
    assert snap is not None
    # Whichever thread won the last swap, the snapshot path is one of
    # the input dirs (resolved). No interleaved garbage.
    assert snap.path in {d.resolve() for d in dirs}


# ── clear() ───────────────────────────────────────────────────────────────


def test_clear_resets_to_no_active_project(tmp_path: Path) -> None:
    """``clear()`` mirrors ``DELETE /api/projects/{id}`` (spec §5.2 line 222).

    Returns to "no project open" but DOES bump the generation — a
    clear is a state change observers should see.
    """
    carrier = ActiveProjectCarrier()
    carrier.set_active_project(tmp_path)
    assert carrier.snapshot() is not None
    assert carrier.generation == 1

    carrier.clear()
    assert carrier.snapshot() is None
    assert carrier.generation == 2


def test_clear_on_empty_carrier_is_noop_but_increments_generation() -> None:
    """Idempotency choice (documented): clear-on-empty still bumps generation.

    This keeps the contract "every successful operation bumps the
    counter" simple. If a future consumer wants "only-if-changed"
    semantics, they can check ``snapshot()`` before clearing.
    """
    carrier = ActiveProjectCarrier()
    carrier.clear()
    assert carrier.snapshot() is None
    assert carrier.generation == 1
