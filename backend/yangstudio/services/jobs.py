"""A small in-process registry for long-running work.

Some operations — fetching a few hundred schemas over NETCONF at roughly a
second each — take long enough that the user must be able to start them and
walk away. Holding that work inside a request means it dies with the page.

Jobs run on a background thread, report progress as they go, and stay in the
registry after finishing so the UI can show what happened even if nobody was
watching at the time. State is deliberately in-process: it is progress
reporting, not a durable queue, and it resets with the server.
"""
from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

# Keep finished jobs around so a user returning to the page can still see the
# outcome, but do not grow without bound.
_MAX_HISTORY = 50

# NETCONF sessions are pooled per device; a couple of workers is plenty and
# keeps concurrent RPCs on any one device modest.
_MAX_WORKERS = 2

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"

TERMINAL = {SUCCEEDED, FAILED, CANCELLED}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Job:
    """One unit of background work and everything the UI needs to render it."""

    id: str
    kind: str                    # e.g. "download-schemas"
    label: str                   # human summary, e.g. "12 schemas from edge-router-1"
    status: str = QUEUED
    total: int = 0
    done: int = 0
    current: str = ""            # what it is working on right now
    message: str = ""            # final summary, or the failure reason
    errors: dict = field(default_factory=dict)
    result: dict = field(default_factory=dict)
    created: str = field(default_factory=_now)
    started: str = ""
    finished: str = ""

    @property
    def percent(self) -> int:
        if self.status in TERMINAL:
            return 100
        if not self.total:
            return 0
        return min(100, int(self.done / self.total * 100))

    def dict(self) -> dict:
        data = asdict(self)
        data["percent"] = self.percent
        return data


class JobHandle:
    """What a running job function uses to report progress and check for cancel."""

    def __init__(self, job: Job, cancel_event: threading.Event, lock: threading.Lock):
        self._job = job
        self._cancel = cancel_event
        self._lock = lock

    @property
    def id(self) -> str:
        return self._job.id

    def set_total(self, total: int) -> None:
        with self._lock:
            self._job.total = total

    def set_progress(self, done: int, current: str = "") -> None:
        """Set absolute progress. Absolute avoids drift if a step is skipped."""
        with self._lock:
            self._job.done = max(0, done)
            self._job.current = current

    def record_error(self, key: str, message: str) -> None:
        with self._lock:
            self._job.errors[key] = message

    def cancelled(self) -> bool:
        return self._cancel.is_set()


class _Registry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._cancels: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        # Deliberately not a ThreadPoolExecutor: it registers an atexit hook
        # that *joins* its workers, so a long job (a few hundred RPCs can run
        # for minutes) would block interpreter shutdown — and with it uvicorn's
        # --reload. Daemon threads let the process exit regardless; a semaphore
        # gives the same concurrency cap.
        self._slots = threading.Semaphore(_MAX_WORKERS)

    def submit(self, kind: str, label: str, fn: Callable[[JobHandle], dict]) -> Job:
        """Register a job and start it. Returns the job immediately."""
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, label=label)
        cancel = threading.Event()
        with self._lock:
            self._jobs[job.id] = job
            self._cancels[job.id] = cancel
            self._order.append(job.id)
            self._evict_locked()
        handle = JobHandle(job, cancel, self._lock)
        thread = threading.Thread(
            target=self._run,
            args=(job, handle, fn),
            name=f"job-{job.id}",
            daemon=True,
        )
        thread.start()
        return job

    def _run(self, job: Job, handle: JobHandle, fn: Callable[[JobHandle], dict]) -> None:
        # Queue behind the concurrency cap without holding a pool thread.
        self._slots.acquire()
        with self._lock:
            job.status = RUNNING
            job.started = _now()
        try:
            result = fn(handle)
            with self._lock:
                if handle.cancelled():
                    job.status = CANCELLED
                    job.message = f"Cancelled after {job.done} of {job.total}"
                else:
                    job.status = SUCCEEDED
                    job.result = result or {}
                    job.message = str((result or {}).get("message", "")) or "Done"
        except Exception as exc:
            with self._lock:
                job.status = FAILED
                job.message = f"{type(exc).__name__}: {exc}"
            # The traceback is for the server log; the UI gets the message.
            traceback.print_exc()
        finally:
            self._slots.release()
            with self._lock:
                job.finished = _now()
                job.current = ""

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        """Newest first."""
        with self._lock:
            return [self._jobs[i] for i in reversed(self._order) if i in self._jobs]

    def cancel(self, job_id: str) -> bool:
        """Ask a job to stop. It stops at its next checkpoint, not instantly."""
        with self._lock:
            job = self._jobs.get(job_id)
            event = self._cancels.get(job_id)
            if job is None or event is None or job.status in TERMINAL:
                return False
        event.set()
        return True

    def clear_finished(self) -> int:
        with self._lock:
            finished = [i for i in self._order if self._jobs[i].status in TERMINAL]
            for job_id in finished:
                self._jobs.pop(job_id, None)
                self._cancels.pop(job_id, None)
                self._order.remove(job_id)
            return len(finished)

    def _evict_locked(self) -> None:
        """Drop the oldest finished jobs once history grows too long."""
        while len(self._order) > _MAX_HISTORY:
            for job_id in list(self._order):
                if self._jobs[job_id].status in TERMINAL:
                    self._jobs.pop(job_id, None)
                    self._cancels.pop(job_id, None)
                    self._order.remove(job_id)
                    break
            else:
                return   # Nothing finished to evict; let it exceed the cap.


    def cancel_all(self) -> int:
        """Signal every running job to stop — used on server shutdown."""
        with self._lock:
            active = [i for i, j in self._jobs.items() if j.status not in TERMINAL]
            events = [self._cancels[i] for i in active if i in self._cancels]
        for event in events:
            event.set()
        return len(active)


registry = _Registry()
