"""``ProjectState`` — the per-project graph (M2 skeleton).

Spec authority:

- ``docs/architecture/00-overview.md`` lines 185-187 — "``ProjectState`` (per
  project) — knows the loaded ``Project``, the current page index, the
  per-page-index ``PageState`` map, the GT map."
- ``specs/16-milestones.md`` line 158 (M2 backend bullet 1) —
  ``core/project_state.py`` ships ``ProjectState`` minus per-page work.
- ``docs/architecture/01-data-models.md §1`` — ``Project`` model lives in
  ``core/models.py``.

What this iter-4 skeleton ships:

- ``PageState`` — *placeholder* dataclass with just ``page_index``.
  The rich version (``pd_book_tools.ocr.page.Page`` object, dirty
  flags, selection sets, per-line/per-word event hooks per
  ``docs/architecture/00-overview.md`` line 187-189) is M3 territory.
- ``ProjectState`` — mutable container holding the active
  ``Project | None``, a ``dict[int, PageState]`` map, a current-page
  cursor, and a monotonically-increasing generation counter for
  SSE / cache-invalidation. Same lock discipline as
  ``ActiveProjectCarrier`` — ``threading.Lock`` (not ``asyncio.Lock``)
  because route handlers may be either sync (threadpool worker) or
  async (event loop), and a thread-lock is safe to hold from both.

Relationship to ``ActiveProjectCarrier``:

- ``ActiveProjectCarrier`` (``core/active_project.py``) holds the
  *pointer*: which project root is currently open. It validates
  filesystem state (``is_dir`` + readable). M2 slice 4 wires
  ``POST /api/projects/load`` to mutate it.
- ``ProjectState`` (this module) holds the *graph*: the loaded
  ``Project`` model + per-page state. It does NOT validate the
  filesystem — by the time a ``Project`` is constructed, slice-5
  persistence has already verified the disk layout. ``ProjectState``
  is a pure in-memory carrier.

What this iter-4 skeleton deliberately does NOT do (deferred):

- **Construct ``Project`` from disk.** That's slice-5 persistence
  (``core/persistence/project_envelope.py`` per
  ``specs/16-milestones.md`` line 159). When it lands, the
  ``POST /api/projects/load`` route will: (a) call slice-5 to read
  ``pages.json`` / ``pages_manifest.json`` and build a ``Project``,
  (b) call ``state.set_loaded_project(project)`` here, (c) extend the
  response to spec-canonical ``LoadProjectResponse`` (replacing
  ``LoadProjectResponseStub``).
- **Per-page work** (line/word matches, OCR, selection state). M3.
- **GT lookup** (``find_ground_truth_text`` per spec §1 line 630).
  Spec calls this method on ``ProjectState`` but the actual GT is
  carried on ``Project.ground_truth_map``; the method itself lands
  with the slice-5 persistence layer that populates the map.
- **Multi-project map.** Spec ``§00`` line 193 says
  "``AppState`` with one ``ProjectState`` per project the user has
  opened in this server lifetime." This iter ships a *single*
  ``ProjectState`` carrier — multi-project bookkeeping is M2-proper
  when ``GET /api/projects/{id}`` lands and needs to look up by id.

Why ``ProjectState`` is iter-4 even though slice-5 persistence is
deferred: ships the contract surface so the route layer stops
returning the slim ``LoadProjectResponseStub`` once persistence lands —
no further route refactor needed, just an additive response-shape
change. (See ``api/projects.py`` ``LoadProjectResponseStub`` docstring
for the symmetric view from the route side.)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from .models import Project, Selection


@dataclass
class PageState:
    """Placeholder per-page state — M3 will replace this with the rich shape.

    Spec ``§00-overview.md`` lines 187-189 names the M3-proper fields:
    the underlying ``pd_book_tools.ocr.page.Page`` object, dirty flags,
    line/word selection sets, the in-memory image, per-line/per-word
    event hooks. None of those are needed for the M2 contract; only
    the ``page_index`` (so the ``ProjectState.page_states`` map's keys
    can be cross-checked against the values) is load-bearing.

    Slice 8b adds the ``page_record`` field as the in-memory cache slot
    that ``core/page_state.ensure_page_model`` writes after a
    successful load. Typed ``Any`` to avoid a circular import between
    ``project_state`` and ``page_state``. M3-proper will tighten the
    annotation to ``PageRecord | None`` once that lives in
    ``core/models.py``.

    Not frozen: M3 will add mutable selection-set fields. The carrier
    above doesn't depend on frozenness — it depends on the ``page_index``
    cross-check, which ``__post_init__`` doesn't enforce on its own.

    ``generation`` / ``last_saved_generation`` (spec-23-B2 / spec §4 + §8):
    ``generation`` bumps on every mutation that "dirties" the in-memory
    page (OCR reload, future word/line/paragraph edits in spec-23-C/D/E).
    ``last_saved_generation`` is updated by ``persist_page_to_file``
    callers (``POST .../save`` and the ``save_project`` job) to mark
    the on-disk labeled envelope as current. ``generation >
    last_saved_generation`` is the dirty-page predicate the
    ``save_project`` job iterates over.
    """

    page_index: int
    page_record: Any = field(default=None)
    generation: int = 0
    last_saved_generation: int = 0
    # Per-page UI selection (spec-23-E §10). Mutated by
    # ``POST /api/projects/{id}/pages/{idx}/selection`` via
    # ``core.selection.apply_selection``. Default is empty — both
    # ``GET /pages/{idx}`` and the spec-23-A ``_page_payload`` helper
    # read ``pstate.selection`` and echo it onto ``PagePayload``.
    selection: Selection = field(default_factory=Selection)
    # Per-character bbox sidecar — keyed by ``"{line_index}_{word_index}"``.
    # Written by ``POST .../words/{li}/{wi}/char-bboxes`` and surfaced
    # onto ``WordMatch.char_bboxes`` in ``_page_payload``.
    # Persisted into ``word_attributes[key]["char_bboxes"]`` in the
    # saved envelope so they survive page reloads.
    char_bboxes_map: dict[str, object] = field(default_factory=dict)
    # Per-word char-range sidecar — keyed by ``"{line_index}_{word_index}"``.
    # Written by ``POST .../words/{li}/{wi}/char-ranges`` and surfaced
    # onto ``WordMatch.char_ranges`` in ``_page_payload``.
    # Mirrors the char_bboxes_map pattern; stored as list[dict] (API shape).
    char_ranges_map: dict[str, object] = field(default_factory=dict)


class ProjectState:
    """Per-project graph: loaded ``Project`` + per-page state map.

    One instance lives on ``app.state.project_state`` (when wired —
    iter-5+ will add the bootstrap step). Mutated under a
    ``threading.Lock`` so concurrent route handlers (sync via
    threadpool, async via event loop) can safely call ``set_*``
    methods without lost updates on the ``generation`` counter.

    Generation contract (mirrors ``ActiveProjectCarrier``):
    every successful mutation bumps ``generation`` by exactly one.
    ``generation == 0`` means "fresh, never touched"; consumers can
    diff against a remembered value to detect "the project state
    changed under me" without diffing the whole graph.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded_project: Project | None = None
        self._page_states: dict[int, PageState] = {}
        self._current_page_index: int = 0
        self._generation: int = 0
        # Per-page locks for serializing concurrent mutations on the same
        # page (spec 23 §13). Lazily created on first access via
        # ``get_page_lock``; the dict itself is guarded by ``self._lock``.
        # threading.Lock (not asyncio.Lock): route handlers are sync
        # (threadpool workers), and threading.Lock is safe to take from
        # both sync and async contexts via FastAPI's threadpool dispatch.
        self._page_locks: dict[int, threading.Lock] = {}

    # ── read-only views ──────────────────────────────────────────────────

    @property
    def loaded_project(self) -> Project | None:
        """The currently loaded ``Project``, or ``None`` if nothing's loaded.

        Returns the same instance that was passed to
        ``set_loaded_project`` — ``Project`` is a Pydantic model, not a
        frozen dataclass, but mutation-through-reference would only
        affect the local copy; the carrier doesn't *re-read* this
        field, it always treats whatever's stored as the source of
        truth at the moment a caller asks.
        """
        return self._loaded_project

    @property
    def page_states(self) -> dict[int, PageState]:
        """The per-page-state map.

        Returns the *internal* dict so consumers can ``len()`` /
        ``in`` / iterate cheaply. Mutation through this reference
        would bypass the lock and the generation counter — callers
        that need to mutate must go through ``set_page_state`` /
        ``clear``. Tests assert by-equality against ``{}`` rather
        than asserting identity, so future hardening (``MappingProxyType``
        wrapper) won't break the test contract.
        """
        return self._page_states

    @property
    def current_page_index(self) -> int:
        """0-based current-page cursor.

        Initialized to 0 on a fresh carrier; ``set_loaded_project``
        seeds it from ``Project.current_page_index``;
        ``set_current_page_index`` is the explicit setter.
        """
        return self._current_page_index

    @property
    def generation(self) -> int:
        """Monotonically-increasing mutation counter.

        Bumped on every successful: ``set_loaded_project``, ``clear``,
        ``set_page_state``, ``set_current_page_index``. Read-only by
        design; written only inside the lock.
        """
        return self._generation

    # ── mutations ────────────────────────────────────────────────────────

    def set_loaded_project(self, project: Project) -> None:
        """Swap to a newly-loaded ``Project``; reset per-page state.

        Per-page state ``PageState`` instances are scoped to a single
        ``Project`` (page indices index into that project's
        ``image_paths``), so loading a different project must clear
        the map — leaving stale entries would silently mis-attribute
        them to the new project.

        Seeds ``current_page_index`` from
        ``Project.current_page_index`` so resume-from-disk behavior
        matches the legacy labeler (which persists the cursor in
        ``project.json``).

        Bumps ``generation`` by 1 (this whole swap is one observable
        state change, not multiple).
        """
        with self._lock:
            self._loaded_project = project
            self._page_states = {}
            self._page_locks = {}
            self._current_page_index = project.current_page_index
            self._generation += 1

    def clear(self) -> None:
        """Reset to empty: no project loaded, no page states.

        Mirrors ``ActiveProjectCarrier.clear`` — every state change
        is observable, so ``generation`` bumps even when "clearing
        an already-empty carrier" wouldn't logically need to. This
        keeps the contract simple ("every mutation method bumps
        generation, full stop").
        """
        with self._lock:
            self._loaded_project = None
            self._page_states = {}
            self._page_locks = {}
            self._current_page_index = 0
            self._generation += 1

    def get_page_lock(self, page_index: int) -> threading.Lock:
        """Return (creating if needed) the per-page mutation lock.

        Spec 23 §13 calls for per-page locking so concurrent mutations
        from the same SPA client (e.g. React 19 transitions) serialize
        on a single page without blocking edits on other pages.

        The spec text says ``asyncio.Lock``, but the route handlers in
        this codebase are sync (threadpool workers via FastAPI), so we
        use ``threading.Lock`` for symmetry with the rest of the project
        carrier locking discipline.

        Lazy: the lock is created on first access, not at
        ``set_loaded_project`` time. Bounded by ``total_pages`` over the
        project lifetime; cleared together with ``_page_states`` on
        ``set_loaded_project`` / ``clear`` (a new project must not share
        locks with the previous one — different page indices, different
        consumers).
        """
        with self._lock:
            lock = self._page_locks.get(page_index)
            if lock is None:
                lock = threading.Lock()
                self._page_locks[page_index] = lock
            return lock

    def get_page_state(self, page_index: int) -> PageState | None:
        """Return the ``PageState`` for ``page_index`` or ``None``.

        Returns ``None`` (not raises ``KeyError``) for missing
        indices — the common caller pattern is "do I have state for
        this page yet?", which a None-check expresses cleanly.
        """
        return self._page_states.get(page_index)

    def set_page_state(self, page_index: int, state: PageState) -> None:
        """Store ``state`` under ``page_index``.

        Validation:

        - ``page_index >= 0`` (per ``docs/architecture/00-overview.md`` "0-based
          ``idx0``" — see the URL-shape rule the spec enforces against
          public route paths).
        - ``state.page_index == page_index`` — the dict key and the
          stored value must agree; otherwise downstream code that
          pulls a ``PageState`` from the map and trusts its
          ``page_index`` field would silently misbehave.

        Bumps ``generation`` by 1 on success.
        """
        if page_index < 0:
            raise ValueError(f"page_index must be non-negative, got {page_index}")
        if state.page_index != page_index:
            raise ValueError(
                f"page_index mismatch: dict key {page_index} != state.page_index {state.page_index}"
            )
        with self._lock:
            self._page_states[page_index] = state
            self._generation += 1

    def set_current_page_index(self, page_index: int) -> None:
        """Update the current-page cursor.

        Validation:

        - ``page_index >= 0``.
        - If a ``Project`` is loaded, ``page_index < total_pages``.
          Without a loaded project we can't validate the upper bound,
          so the only cheap check is the non-negative one (which also
          fires when no project is loaded).

        Bumps ``generation`` by 1 on success.
        """
        if page_index < 0:
            raise ValueError(f"current_page_index must be non-negative, got {page_index}")
        # Snapshot the loaded project under the lock so we don't race a
        # concurrent set_loaded_project / clear and validate against a
        # stale total_pages.
        with self._lock:
            project = self._loaded_project
            if project is not None and page_index >= project.total_pages:
                raise ValueError(
                    f"current_page_index {page_index} out of range for project with "
                    f"total_pages={project.total_pages}"
                )
            self._current_page_index = page_index
            self._generation += 1


__all__ = ["PageState", "ProjectState"]
