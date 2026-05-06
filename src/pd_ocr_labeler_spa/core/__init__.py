"""Core domain modules — settings-agnostic logic, no FastAPI / no I/O at import time.

M1 ships ``exceptions`` (the spec-named ``NotImplementedYet``). Later
milestones add ``app_state``, ``project_state``, ``page_state``,
``persistence/`` etc. per ``specs/02-backend.md §1``.
"""
