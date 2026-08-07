"""In-memory cooperative cancellation signals for background scan jobs.

Scan/lineage workers run as plain sync callables via FastAPI's
`BackgroundTasks`, which executes them in a worker thread -- there is no
way to forcibly kill a running thread in Python. Instead, a cancel request
just sets a flag here; the worker checks it at safe checkpoints (between
databases, between views) and stops itself, marking the job CANCELLED.

This registry is process-local. It is intentionally NOT persisted, since a
cancel request only ever needs to reach the worker thread running inside
this same process -- if the backend restarts, every in-flight job is gone
anyway (see scan_worker.py/lineage_worker.py, which is why restarting the
container was the only way to stop a job before this existed).
"""

import threading

_cancelled_job_ids: set[str] = set()
_lock = threading.Lock()


def request_cancel(job_id: str) -> None:
    with _lock:
        _cancelled_job_ids.add(job_id)


def is_cancelled(job_id: str) -> bool:
    with _lock:
        return job_id in _cancelled_job_ids


def clear(job_id: str) -> None:
    with _lock:
        _cancelled_job_ids.discard(job_id)
