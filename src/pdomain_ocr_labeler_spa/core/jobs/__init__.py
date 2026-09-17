"""In-process job infrastructure — broker + runner.

Spec authority: ``docs/architecture/02-backend.md §11``.
"""

from .events import JobEventBroker
from .runner import (
    Job,
    JobRunner,
    JobStatus,
    payload_result_keys,
    registered_handlers,
    registered_job_types,
    to_public_job,
)

__all__ = [
    "Job",
    "JobEventBroker",
    "JobRunner",
    "JobStatus",
    "payload_result_keys",
    "registered_handlers",
    "registered_job_types",
    "to_public_job",
]
