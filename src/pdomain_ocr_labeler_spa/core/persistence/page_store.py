"""Project-scoped event store + blob store for labeler-spa.

``LabelerPageStore`` wraps ``pdomain_ops.page_aggregate.PagesApplication``
and ``pdomain_ops.blob_store.BlobStore`` for one project directory. It is
the single persistence entry point — the OCR adapter writes here, the API
reads here.

Storage layout::

    <project_dir>/.pd-pages/
        events.db   ← eventsourcing SQLite: PageAggregate + ProjectAggregate events
        blobs/      ← content-addressed: PNG images, thumbnails, Page JSON

``LabelerPageStore`` is NOT a global singleton. Each loaded project gets its
own instance initialised at project-load time and stashed on ``app.state``.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from pdomain_ops.blob_store import BlobStore
from pdomain_ops.page_aggregate import PageAggregate, PagesApplication, ProjectAggregate
from pdomain_ops.page_server import LocalPageStore


class LabelerPageStore:
    """One-project façade: event store + blob store.

    Parameters
    ----------
    project_dir:
        Root directory of the project (the directory that contains the
        source images). The ``.pd-pages/`` subdirectory is created here.
    """

    def __init__(self, project_dir: Path) -> None:
        pd_pages = Path(project_dir) / ".pd-pages"
        pd_pages.mkdir(parents=True, exist_ok=True)
        # Use env= parameter (not os.environ) to avoid polluting other tests
        # running in parallel. Each store gets its own SQLite DB.
        self._app = PagesApplication(
            env={
                "PERSISTENCE_MODULE": "eventsourcing.sqlite",
                "SQLITE_DBNAME": str(pd_pages / "events.db"),
            }
        )
        self._inner = LocalPageStore(self._app)
        # BlobStore under .pd-pages/blobs/ to keep everything co-located
        self.blobs = BlobStore(pd_pages)

    # ── PageStore delegation ─────────────────────────────────────────────

    def save_page(self, aggregate: PageAggregate) -> None:
        """Save (create or update) a PageAggregate."""
        self._inner.save_page(aggregate)

    def get_page(self, page_id: UUID) -> PageAggregate:
        """Load a PageAggregate by page_id."""
        return self._inner.get_page(page_id)

    def save_project(self, aggregate: ProjectAggregate) -> None:
        """Save (create or update) a ProjectAggregate."""
        self._inner.save_project(aggregate)

    def get_project(self, project_id: UUID) -> ProjectAggregate:
        """Load a ProjectAggregate by project_id."""
        return self._inner.get_project(project_id)

    def close(self) -> None:
        """Close the underlying PagesApplication (flush + disconnect)."""
        self._app.close()


__all__ = ["LabelerPageStore"]
