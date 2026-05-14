"""HTTP middleware for ``pd-ocr-labeler-spa``.

Per ``docs/architecture/02-backend.md §9`` the ``RequestIdMiddleware`` is a verbatim
port from ``pd-prep-for-pgdp``: it stamps every request with a
correlation id so log lines emitted from inside the request (and from
``lifespan`` / exception handlers / SPA fallback) can be traced back to
a single user-facing call.
"""
