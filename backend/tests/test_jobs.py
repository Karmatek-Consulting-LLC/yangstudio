"""The job registry backs the task drawer, so its state machine matters."""
import threading
import time

import pytest

from yangstudio.services.jobs import CANCELLED, FAILED, SUCCEEDED, _Registry


@pytest.fixture
def registry():
    return _Registry()


def _wait_for(registry, job_id, *, timeout=5.0):
    """Block until the job reaches a terminal state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = registry.get(job_id)
        if job and job.status in (SUCCEEDED, FAILED, CANCELLED):
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def test_submit_returns_immediately_and_completes(registry):
    release = threading.Event()

    def work(handle):
        handle.set_total(3)
        release.wait(timeout=5)
        handle.set_progress(3)
        return {"message": "all done"}

    job = registry.submit("test", "unit", work)
    # The call returned before the work finished — that is the whole point.
    assert job.status in ("queued", "running")
    release.set()
    finished = _wait_for(registry, job.id)
    assert finished.status == SUCCEEDED
    assert finished.message == "all done"
    assert finished.percent == 100


def test_progress_is_absolute_and_reported(registry):
    seen = threading.Event()

    def work(handle):
        handle.set_total(10)
        handle.set_progress(4, "step-four")
        seen.set()
        time.sleep(0.2)
        return {}

    job = registry.submit("test", "unit", work)
    assert seen.wait(timeout=5)
    mid = registry.get(job.id)
    assert mid.done == 4
    assert mid.total == 10
    assert mid.percent == 40
    assert mid.current == "step-four"
    _wait_for(registry, job.id)


def test_cancel_stops_at_next_checkpoint(registry):
    started = threading.Event()

    def work(handle):
        handle.set_total(100)
        started.set()
        for i in range(100):
            if handle.cancelled():
                break          # Cooperative: we stop where we choose to check.
            handle.set_progress(i)
            time.sleep(0.01)
        return {}

    job = registry.submit("test", "unit", work)
    assert started.wait(timeout=5)
    assert registry.cancel(job.id) is True
    finished = _wait_for(registry, job.id)
    assert finished.status == CANCELLED
    assert "Cancelled after" in finished.message
    assert finished.done < 100


def test_cancelling_a_finished_job_is_a_no_op(registry):
    job = registry.submit("test", "unit", lambda handle: {})
    _wait_for(registry, job.id)
    assert registry.cancel(job.id) is False


def test_failure_is_captured_not_raised(registry):
    def work(handle):
        raise ValueError("device exploded")

    job = registry.submit("test", "unit", work)
    finished = _wait_for(registry, job.id)
    assert finished.status == FAILED
    assert "ValueError: device exploded" in finished.message


def test_errors_are_recorded_without_failing_the_job(registry):
    def work(handle):
        handle.set_total(2)
        handle.record_error("bad-module", "not found")
        handle.set_progress(2)
        return {"message": "1 of 2"}

    job = registry.submit("test", "unit", work)
    finished = _wait_for(registry, job.id)
    assert finished.status == SUCCEEDED       # Partial failure is still a result.
    assert finished.errors == {"bad-module": "not found"}


def test_clear_finished_keeps_running_jobs(registry):
    release = threading.Event()
    done_job = registry.submit("test", "done", lambda handle: {})
    _wait_for(registry, done_job.id)
    running = registry.submit("test", "running", lambda handle: release.wait(timeout=5))

    assert registry.clear_finished() == 1
    assert registry.get(done_job.id) is None
    assert registry.get(running.id) is not None
    release.set()
    _wait_for(registry, running.id)


def test_listing_is_newest_first(registry):
    first = registry.submit("test", "first", lambda handle: {})
    _wait_for(registry, first.id)
    second = registry.submit("test", "second", lambda handle: {})
    _wait_for(registry, second.id)
    assert [j.label for j in registry.list()][:2] == ["second", "first"]


def test_job_threads_are_daemons(registry):
    """A long job must not block interpreter shutdown (and so uvicorn reload)."""
    import threading

    release = threading.Event()
    job = registry.submit("test", "long", lambda handle: release.wait(timeout=5))
    running = [t for t in threading.enumerate() if t.name == f"job-{job.id}"]
    assert running and running[0].daemon is True
    release.set()
    _wait_for(registry, job.id)


def test_cancel_all_signals_every_running_job(registry):
    import threading

    release = threading.Event()

    def work(handle):
        while not handle.cancelled():
            if release.wait(timeout=0.02):
                break
        return {}

    jobs = [registry.submit("test", f"j{i}", work) for i in range(2)]
    assert registry.cancel_all() == 2
    for job in jobs:
        assert _wait_for(registry, job.id).status == CANCELLED
