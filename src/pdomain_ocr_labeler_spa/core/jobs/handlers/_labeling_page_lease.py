"""Shared open/bind/close helper for job handlers that read page image bytes.

Spec authority: pdomain-ocr-synth's
``docs/issues/2026-09-16-page-kind-follow-ups-parked-during-tasks-6-and-7.md``
"Still open: a run on a book-labeling project can measure unpinned bytes".
Both ``propose_page_kinds`` and ``propose_regions`` walk many pages in a
book-scoped loop and must read each page's image bytes through a verified
lease on a book-labeling project, the same mechanism
``api/dependencies.bind_page_labeling_lease`` uses per request — reimplemented
here because that provider's own docstring says background jobs acquire their
own lease separately. One shared context manager, rather than each handler
repeating the open/bind/close dance by hand, is what keeps a descriptor leak
in one handler from becoming a second bug to fix in the other.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...project_state import ProjectState


@contextmanager
def leased_labeling_page(project_state: ProjectState, page_index: int) -> Iterator[None]:
    """Open, bind, and unconditionally close one page's verified lease.

    On an ordinary project ``open_labeling_page`` returns ``None`` and the
    subsequent ``bind_labeling_page`` is then a no-op — ``labeling_image_path``
    already resolves the on-disk path with nothing to lease. On a
    book-labeling project this opens a caller-owned descriptor lease scoped
    to the ``with`` block, binds it so every ``labeling_image_path`` call
    made while the block is active — including work later offloaded onto a
    thread via ``asyncio.to_thread``, which propagates the contextvar the
    binding uses — resolves to the sealed ``/proc/self/fd/N`` path, and
    closes the descriptor on exit whether the block succeeded or raised.

    Raises ``ValueError`` (propagated from ``open_labeling_page``) when the
    page's manifest hash fails verification. Callers looping over many pages
    catch that per page and decide whether to skip it; there is no lease to
    close in that case because ``open_labeling_page`` never hands one back.
    """
    lease = project_state.open_labeling_page(page_index)
    try:
        with project_state.bind_labeling_page(page_index, lease):
            yield
    finally:
        if lease is not None:
            lease.close()


__all__ = ["leased_labeling_page"]
