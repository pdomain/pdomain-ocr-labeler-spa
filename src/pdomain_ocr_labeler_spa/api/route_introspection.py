"""Recursively flatten a Starlette/FastAPI app's route tree.

Starlette 1.3 changed ``include_router`` semantics: instead of *flattening*
each sub-router's routes into the parent ``app.router.routes`` list (the
pre-1.3 behaviour), it now appends one lazy ``_IncludedRouter`` matcher per
``include_router`` call. The actual ``APIRoute`` objects live on that
matcher's ``original_router.routes`` rather than on ``app.routes`` directly.

That broke every call site that walked ``app.routes`` expecting flat leaf
routes — both production (``_suppress_ops_schema_violations``) and tests
(route-conformance / path-presence assertions). This helper restores a flat
view by recursing into ``_IncludedRouter.original_router`` (and into any
``Mount``-style nesting via ``.routes``), yielding only leaf route objects.

It is version-tolerant: under pre-1.3 Starlette there are no
``_IncludedRouter`` wrappers, so the recursion degrades to a flat pass and
returns the same leaves it always did.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def iter_leaf_routes(app: FastAPI) -> Iterator[object]:
    """Yield every leaf route object reachable from ``app``.

    A "leaf" is a route that is not itself a container of further routes —
    i.e. a ``Route`` / ``APIRoute`` / ``WebSocketRoute``, not an
    ``_IncludedRouter`` wrapper or a ``Mount``. Use this anywhere you need
    to enumerate concrete routes (e.g. to read ``.path`` or narrow to
    ``APIRoute`` and mutate ``include_in_schema``).
    """
    yield from _walk(app.router.routes)


def _walk(routes: object) -> Iterator[object]:
    if not isinstance(routes, (list, tuple)):
        return
    for route in routes:
        # Starlette 1.3 include_router wrapper: the real routes hang off
        # ``original_router.routes``. Recurse rather than yield the wrapper.
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _walk(getattr(original, "routes", ()))
            continue
        # Mount / sub-Router style nesting (e.g. ``app.mount`` with an
        # inner ``Router``): recurse into its ``.routes`` when present AND
        # the node has no ``.path`` of its own to treat as a leaf. We only
        # recurse for container types that aren't themselves a path route.
        sub = getattr(route, "routes", None)
        if sub is not None and getattr(route, "path", None) is None:
            yield from _walk(sub)
            continue
        yield route


def iter_leaf_route_paths(app: FastAPI) -> set[str]:
    """Return the set of ``.path`` values across all leaf routes.

    Routes without a ``.path`` attribute are skipped (e.g. lifespan-only
    nodes). Useful for presence assertions like ``"/env.js" in paths``.
    """
    paths: set[str] = set()
    for route in iter_leaf_routes(app):
        path = getattr(route, "path", None)
        if path is not None:
            paths.add(path)
    return paths


__all__ = ["iter_leaf_route_paths", "iter_leaf_routes"]
