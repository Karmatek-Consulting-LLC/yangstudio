"""Downloads must not be able to grind for hours on a dead session.

A device advertising 500 modules, each RPC bounded at RPC_TIMEOUT, is hours of
work if the session dies early. These pin the guard against that.
"""
from unittest.mock import patch

import pytest
from ncclient.operations import RPCError

from yangstudio.core.devices import Device
from yangstudio.services import netconf


@pytest.fixture
def device():
    return Device.create("r1", address="10.0.0.1", username="u", password="p")


class FakeConnection:
    """Stands in for an ncclient Manager, with scripted per-module outcomes."""

    def __init__(self, outcomes: dict):
        self.outcomes = outcomes
        self.asked: list[str] = []

    def get_schema(self, name):
        self.asked.append(name)
        outcome = self.outcomes.get(name, "ok")
        if isinstance(outcome, Exception):
            raise outcome
        return type("Reply", (), {"data": f"module {name} {{}}"})()


def _rpc_error(message="no such schema"):
    """An RPCError without going through ncclient's XML parsing."""
    error = RPCError.__new__(RPCError)
    Exception.__init__(error, message)
    return error


def _run(device, modules, outcomes):
    connection = FakeConnection(outcomes)
    with patch("yangstudio.services.netconf.get_session", return_value=connection):
        with patch("yangstudio.services.netconf.close_session") as closer:
            result = netconf.download_schemas(device, modules)
    return result, connection, closer


def test_all_succeed(device):
    modules = [f"mod-{i}" for i in range(5)]
    result, connection, _ = _run(device, modules, {})
    assert sorted(result["schemas"]) == sorted(modules)
    assert result["errors"] == {}
    assert result["aborted"] == ""
    assert connection.asked == modules


def test_transport_failures_trip_the_breaker(device):
    """Consecutive transport errors mean the session is gone — stop early."""
    modules = [f"mod-{i}" for i in range(100)]
    outcomes = {name: OSError("socket closed") for name in modules}
    result, connection, closer = _run(device, modules, outcomes)

    assert len(connection.asked) == netconf.MAX_CONSECUTIVE_FAILURES
    assert "session looks dead" in result["aborted"]
    # The dead session is dropped so the next attempt reconnects.
    closer.assert_called_once_with(device.slug)


def test_rpc_errors_do_not_trip_the_breaker(device):
    """A device saying 'no such schema' is about that module, not the session."""
    modules = [f"mod-{i}" for i in range(20)]
    outcomes = {name: _rpc_error() for name in modules[:10]}
    result, connection, closer = _run(device, modules, outcomes)

    assert len(connection.asked) == 20            # ran the whole list
    assert result["aborted"] == ""
    assert len(result["errors"]) == 10
    assert len(result["schemas"]) == 10
    closer.assert_not_called()


def test_a_success_resets_the_breaker(device):
    """Intermittent failures should not accumulate into a false abort."""
    modules = [f"mod-{i}" for i in range(12)]
    # Fail in pairs, never MAX_CONSECUTIVE_FAILURES in a row.
    outcomes = {
        name: OSError("blip") for i, name in enumerate(modules) if i % 3 != 2
    }
    result, connection, _ = _run(device, modules, outcomes)
    assert len(connection.asked) == 12
    assert result["aborted"] == ""


def test_cancellation_stops_the_loop(device):
    modules = [f"mod-{i}" for i in range(50)]
    seen: list[str] = []

    def should_cancel():
        return len(seen) >= 3

    connection = FakeConnection({})
    with patch("yangstudio.services.netconf.get_session", return_value=connection):
        netconf.download_schemas(
            device,
            modules,
            on_progress=lambda name, i, total: seen.append(name),
            should_cancel=should_cancel,
        )
    assert len(connection.asked) < 10        # stopped early, did not run all 50


def test_progress_reports_every_module(device):
    modules = [f"mod-{i}" for i in range(4)]
    calls = []
    connection = FakeConnection({})
    with patch("yangstudio.services.netconf.get_session", return_value=connection):
        netconf.download_schemas(
            device, modules, on_progress=lambda n, i, t: calls.append((n, i, t))
        )
    assert calls == [("mod-0", 1, 4), ("mod-1", 2, 4), ("mod-2", 3, 4), ("mod-3", 4, 4)]
