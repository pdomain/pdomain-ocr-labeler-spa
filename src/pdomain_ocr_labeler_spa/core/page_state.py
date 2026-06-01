"""``core/page_state.ensure_page_model`` — slice-8b contract scaffold.

Spec authority:

- ``specs/16-milestones.md`` line 235 — "``core/page_state.py`` —
  minimal version: ``ensure_page_model`` (load cache > load saved
  > run OCR), ``_resolve_save_directory``, ``persist_page_to_file``."
- ``docs/architecture/09-persistence.md`` lines 32–40 — load precedence:
  labeled-lane → cached-lane → run OCR → fallback. The SPA preserves
  this exact precedence.
- Legacy reference: ``pd-ocr-labeler/pd_ocr_labeler/state/
  project_state.py:420`` (``ensure_page_model``).

What this slice ships:

- ``PageSource`` enum mirroring the spec'd ``PageSource`` (per
  ``docs/architecture/01-data-models.md §1`` lines 55–59); the canonical
  pydantic ``PageSource`` will eventually live in ``core/models.py``
  alongside ``PageRecord`` (M3-proper). It's defined locally here as
  a ``StrEnum`` so this slice doesn't depend on the M3-proper
  ``PageRecord`` import — see the contract docstring on
  ``PageLoadOutcome`` below for the seam.
- ``PageLoadOutcome`` — placeholder result type holding
  ``page_index``, ``source``, and an ``Any`` ``payload`` slot. M3-proper
  will replace this with ``PageRecord`` (per ``docs/architecture/01-data-models.md
  §1.PageRecord``); ``ensure_page_model``'s contract (idempotency,
  precedence, lock discipline) is invariant under that swap.
- ``PageLoader`` — the dispatch protocol:
  ``load_labeled / load_cached / run_ocr``. The real implementation
  (``LocalDoctrPageLoader``) wires ``IStorage`` + ``IOCREngine`` +
  ``core/persistence/user_page_envelope.py`` and lands when M3-proper
  pulls in pdomain_book_tools. Right now the contract is loader-agnostic
  so test suites stub it without importing pdomain_book_tools.
- ``ensure_page_model`` — the dispatcher itself. Pure logic over
  ``ProjectState`` + a ``PageLoader``; no I/O.

What this slice deliberately does NOT do (deferred):

- **The actual DocTR run.** The real ``LocalDoctrPageLoader.run_ocr``
  pulls in pdomain_book_tools.Page, the predictor cache from
  ``core/ocr/predictor.py``, and OCR provenance — all M3-proper.
- **``PageRecord`` construction.** Spec §1 says ``PageRecord`` is the
  metadata wrapper around ``Page``; until ``Page`` is in scope we
  return a placeholder ``PageLoadOutcome``.
- **``_resolve_save_directory`` and ``persist_page_to_file``.** Both
  named on the M3 milestone bullet; both depend on
  ``core/persistence/user_page_envelope.py`` which is a separate
  M3 slice.
- **Auto-cache write after first OCR.** Listed in the same M3 bullet;
  layered on top of the cache write side of persistence.
- **Ground-truth injection.** Legacy ``ensure_page_model:728-748``
  attaches GT lines onto the page after loading; depends on
  ``Project.ground_truth_map`` being populated, which is M3 too.

Cache-key shape: ``ProjectState.page_states`` is keyed by raw
``page_index`` (``int``). That's deliberately *not* keyed by
``(project_id, page_index, ocr_config_hash)`` — ``ProjectState`` is
already scoped to one project (one carrier per loaded project), and
swapping OCR config invalidates the whole project state via
``set_loaded_project`` / a future ``invalidate_page_models`` call.
This matches legacy ``project_state.page_models: dict[int, PageModel]``
exactly.

Lock discipline: ``ensure_page_model`` holds ``ProjectState._lock``
across the *entire* load (precedence probes + OCR run + cache write)
to prevent two concurrent callers from both spending OCR cost on the
same page. This is a longer hold than the simple ``set_*`` mutators —
acceptable here because OCR-on-first-load is intrinsically the slow
path, and the lock contention is per-project (one lock per loaded
project, not a global lock).

Exception types:

- ``PageIndexOutOfRangeError(IndexError)`` — page_index < 0 or ≥
  ``Project.total_pages``. Subclasses ``IndexError`` so generic
  index-error handling catches it.
- ``PageImageNotFoundError(FileNotFoundError)`` — the loader couldn't
  find the on-disk image for a page. Subclasses ``FileNotFoundError``
  for the same reason.
- OCR-engine errors propagate verbatim (not wrapped) so the caller
  can distinguish "wrong inputs" from "engine failure"; the failure
  is *not* cached, so the next call retries.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .models import PageSource, Project
from .persistence.paths import labeled_projects_root
from .project_state import PageState, ProjectState


@dataclass(frozen=True)
class PageLoadOutcome:
    """Placeholder result type for ``ensure_page_model``.

    M3-proper replaces this with the spec'd ``PageRecord``
    (``docs/architecture/01-data-models.md §1`` lines 49–80). The
    ``ensure_page_model`` contract (precedence, idempotency, lock
    discipline, exception types) is invariant under that swap —
    consumers of this module that hold a ``PageLoadOutcome`` reference
    will need a one-line rename when ``PageRecord`` lands, but the
    *behavior* won't change.

    ``payload`` is typed ``object`` (not ``Any``) so callers must narrow
    to ``Page`` (or another concrete type) before accessing attributes.
    Tests can pass plain Python objects (``str`` markers, ``object()``
    sentinels) since all types are ``object`` subtypes.
    """

    page_index: int
    source: PageSource
    payload: object


class PageIndexOutOfRangeError(IndexError):
    """``page_index < 0`` or ``page_index >= total_pages``.

    Subclasses ``IndexError`` so callers using
    ``except IndexError:`` for generic page-cursor bounds checks
    (e.g. the route layer's "advance past last page" guard) still
    catch this.
    """


class PageImageNotFoundError(FileNotFoundError):
    """Loader couldn't find the on-disk image for the requested page.

    Subclasses ``FileNotFoundError`` so generic filesystem-error
    handling catches it. The loader is responsible for raising this
    *before* attempting OCR (cheap fail) — the OCR engine itself
    raising on missing input would propagate as the engine's own
    exception type.
    """


@runtime_checkable
class PageLoader(Protocol):
    """Dispatch protocol for the three load lanes.

    The real implementation (``LocalDoctrPageLoader``, M3-proper)
    wires ``IStorage``, ``IOCREngine``, and the persistence-layer
    envelope reader. This slice only nails the *protocol shape* so
    ``ensure_page_model`` can be tested and reviewed independently of
    the heavy machinery.

    Per ``docs/architecture/09-persistence.md`` lines 32–40, the precedence is:

    1. ``load_labeled(page_index)`` — labeled-lane envelope; returns
       ``None`` if no envelope exists.
    2. ``load_cached(page_index)`` — cached-lane envelope; returns
       ``None`` if no envelope exists.
    3. ``run_ocr(page_index)`` — runs OCR; never returns ``None``
       (it either succeeds or raises). On success, the loader is
       *also* responsible for the auto-cache-write side effect (per
       legacy ``project_state.py:780-797``); ``ensure_page_model``
       does not write to the cache itself.
    """

    def load_labeled(self, page_index: int) -> PageLoadOutcome | None: ...
    def load_cached(self, page_index: int) -> PageLoadOutcome | None: ...
    def run_ocr(self, page_index: int) -> PageLoadOutcome: ...


def ensure_page_model(
    state: ProjectState,
    page_index: int,
    *,
    loader: PageLoader,
    force_ocr: bool = False,
) -> PageLoadOutcome | None:
    """Lazy page-load with labeled → cached → OCR precedence.

    Returns the cached ``PageLoadOutcome`` after the first call; the
    second call is an in-memory dict lookup. ``force_ocr=True``
    bypasses both the in-memory cache *and* the labeled/cached lane
    probes, going straight to OCR (legacy parity:
    ``project_state.py:580-585``).

    Returns ``None`` only when no project is loaded (mirrors legacy
    ``ensure_page_model:451-453`` early-return). Out-of-range indices
    *raise* ``PageIndexOutOfRangeError`` — the legacy implementation
    returned ``None`` for those too, but in the SPA the route layer
    has already validated the URL-shape ``page_index ∈ [0,
    total_pages)``, so a None-return on out-of-range would mask a
    bug rather than recover from one.

    Lock contract: holds ``state._lock`` for the entire load,
    including OCR. See module docstring for the rationale (per-project
    lock, OCR is intrinsically the slow path, prevents double-OCR
    under contention).
    """
    project = state.loaded_project
    if project is None:
        return None
    if page_index < 0 or page_index >= project.total_pages:
        raise PageIndexOutOfRangeError(
            f"page_index {page_index} out of range for project with total_pages={project.total_pages}"
        )

    # Hold the project lock across the entire load. Two concurrent
    # callers for the same page_index will serialize here; the second
    # one re-checks the cache after acquiring the lock (the
    # double-checked-locking pattern below).
    with state._lock:
        if not force_ocr:
            existing = state._page_states.get(page_index)
            if existing is not None and existing.page_record is not None:
                return existing.page_record

        # Lane probes happen under the lock so a concurrent
        # ``set_loaded_project`` swap can't shift the project out from
        # under us mid-load.
        outcome: PageLoadOutcome
        if not force_ocr:
            labeled = loader.load_labeled(page_index)
            if labeled is not None:
                outcome = labeled
            else:
                cached = loader.load_cached(page_index)
                outcome = cached if cached is not None else loader.run_ocr(page_index)
        else:
            outcome = loader.run_ocr(page_index)

        # Cache the outcome on the existing PageState (or create one).
        # Note: ``ProjectState.set_page_state`` would re-acquire the
        # lock and bump generation — we're already inside the lock and
        # mutating the dict directly is the cheaper path. Generation
        # bump is still desired so SSE consumers see the new state.
        existing = state._page_states.get(page_index)
        if existing is None:
            existing = PageState(page_index=page_index)
            state._page_states[page_index] = existing
        existing.page_record = outcome
        # Stamp page_id from OCR result if available (M9 event-store wiring).
        # The loader stamps _labeler_page_id on the Page object during run_ocr
        # when a LabelerPageStore is available.
        payload_obj = getattr(outcome, "payload", None)
        labeler_page_id = getattr(payload_obj, "_labeler_page_id", None)
        if labeler_page_id is not None and existing.page_id is None:
            existing.page_id = labeler_page_id
        state._generation += 1
        return outcome


# ──────────────────────────────────────────────────────────────────────────────
# Save-lane helpers
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_save_directory(data_root: Path, project_id: str) -> Path:
    """Return the labeled-lane directory for *project_id* under *data_root*.

    Pure path derivation — no I/O, no mkdir. The directory is
    ``<data_root>/labeled-projects/<project_id>/`` (mirrors
    ``labeled_projects_root`` from ``persistence.paths`` + one
    project-level subdir).

    Spec authority: ``specs/16-milestones.md`` line 240 —
    ``"_resolve_save_directory"``.
    """
    return labeled_projects_root(data_root) / project_id


def persist_page_to_file(
    *,
    page: Any,
    project: Project,
    page_index: int,
    data_root: Path,
    ocr_provenance: Any | None = None,
) -> None:
    """DEPRECATED: UserPageEnvelope lane is retired (greenfield event-store adoption).

    Callers must be updated to use ``save_page_to_store`` from ``core.page_state``
    (M8b). This stub raises ``NotImplementedError`` so tests that still call the
    old path fail loudly instead of silently succeeding with a no-op.
    """
    raise NotImplementedError("persist_page_to_file is retired — use save_page_to_store (M8b).")


def save_page_to_store(
    *,
    page_id: Any,
    changes: list[dict[str, Any]],
    store: Any,  # LabelerPageStore — avoid circular import at runtime
) -> None:
    """Fire a ``LabelerEdited`` event on the PageAggregate and persist.

    Replaces ``persist_page_to_file`` — the event store is the durable
    form; the labeled lane is gone (M5b).

    Parameters
    ----------
    page_id:
        UUID of the page to save.
    changes:
        List of typed dict events describing the edits.
    store:
        The project's ``LabelerPageStore``.
    """
    from datetime import UTC, datetime

    from pdomain_ops.pages import ProvenanceNode

    agg = store.get_page(page_id)
    prov_node = ProvenanceNode(
        id=f"labeler-{datetime.now(UTC).isoformat()}",
        source="labeler",
        tool="labeler-spa",
        timestamp=datetime.now(UTC),
    )
    agg.labeler_edited(provenance_node=prov_node, changes=changes)
    store.save_page(agg)


__all__ = [
    "PageImageNotFoundError",
    "PageIndexOutOfRangeError",
    "PageLoadOutcome",
    "PageLoader",
    "PageSource",
    "_resolve_save_directory",
    "ensure_page_model",
    "persist_page_to_file",
    "save_page_to_store",
]
