"""In-process job infrastructure — broker + runner.

Spec authority: ``docs/architecture/02-backend.md §11``.
"""

from .events import JobEventBroker
from .runner import Job, JobRunner, JobStatus

__all__ = ["Job", "JobEventBroker", "JobRunner", "JobStatus"]
