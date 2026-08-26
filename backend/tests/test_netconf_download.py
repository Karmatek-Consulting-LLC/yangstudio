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


def _run(device, modules, outcomes, follow_dependencies=False):
    connection = FakeConnection(outcomes)
    with patch("yangstudio.services.netconf.get_session", return_value=connection):
        with patch("yangstudio.services.netconf.close_session") as closer:
            result = netconf.download_schemas(
                device, modules, follow_dependencies=follow_dependencies
            )
    return result, connection, closer


def test_all_succeed(device):
    modules = [f"mod-{i}" for i in range(5)]
    result, connection, _ = _run(device, modules, {})
    assert sorted(result["schemas"]) == sorted(modules)
    assert result["errors"] == {}
    assert result["aborted"] == ""
    assert connection.asked == modules


def test_transport_failures_trip_the_breaker(device):
    """Consecutive transport errors mean the device is gone — stop early.

    Each one is retried once on a fresh session first, so the breaker trips
    after MAX_CONSECUTIVE_FAILURES modules, not MAX attempts.
    """
    modules = [f"mod-{i}" for i in range(100)]
    outcomes = {name: OSError("socket closed") for name in modules}
    result, connection, closer = _run(device, modules, outcomes)

    attempted = set(connection.asked)
    assert len(attempted) == netconf.MAX_CONSECUTIVE_FAILURES
    assert "not answering" in result["aborted"]
    # Dropped on every retry, and again when the breaker trips.
    assert closer.called


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
    # Every module is attempted; the failing ones are attempted twice.
    assert set(connection.asked) == set(modules)
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
    # Reported as (module, completed so far, total known now). The total can
    # grow mid-run when a dependency is discovered, so it is sent every time.
    assert calls == [("mod-0", 0, 4), ("mod-1", 1, 4), ("mod-2", 2, 4), ("mod-3", 3, 4)]



# -- dependency following --------------------------------------------------

def _module(name: str, imports: tuple[str, ...] = ()) -> str:
    """Minimal YANG source with the given imports."""
    lines = [f"module {name} {{", f"  namespace 'urn:x:{name}'; prefix p;"]
    lines += [f"  import {dep} {{ prefix {dep[:2]}; }}" for dep in imports]
    lines.append("}")
    return "\n".join(lines)


class DependencyConnection:
    """Serves modules whose sources declare imports."""

    def __init__(self, graph: dict[str, tuple[str, ...]]):
        self.graph = graph
        self.asked: list[str] = []

    def get_schema(self, name):
        self.asked.append(name)
        if name not in self.graph:
            raise OSError(f"no such module {name}")
        return type("Reply", (), {"data": _module(name, self.graph[name])})()


def _run_deps(device, roots, graph, have=None):
    conn = DependencyConnection(graph)
    with patch("yangstudio.services.netconf.get_session", return_value=conn):
        with patch("yangstudio.services.netconf.close_session"):
            result = netconf.download_schemas(device, roots, have=have)
    return result, conn


def test_imports_are_followed_transitively(device):
    """Asking for one module fetches the whole tree beneath it."""
    graph = {"a": ("b",), "b": ("c",), "c": (), "unrelated": ()}
    result, conn = _run_deps(device, ["a"], graph)

    assert set(result["schemas"]) == {"a", "b", "c"}
    assert result["pulled_in"] == ["b", "c"]
    assert "unrelated" not in conn.asked


def test_a_dependency_cycle_terminates(device):
    """Modules can import each other; the walk must not loop."""
    graph = {"a": ("b",), "b": ("a",)}
    result, conn = _run_deps(device, ["a"], graph)

    assert set(result["schemas"]) == {"a", "b"}
    assert len(conn.asked) == 2


def test_modules_already_present_are_not_refetched(device):
    graph = {"a": ("b",), "b": ()}
    result, conn = _run_deps(device, ["a"], graph, have={"b"})

    assert conn.asked == ["a"]
    assert result["pulled_in"] == []


def test_a_dependency_asked_for_explicitly_is_not_double_counted(device):
    graph = {"a": ("b",), "b": ()}
    result, _ = _run_deps(device, ["a", "b"], graph)

    assert set(result["schemas"]) == {"a", "b"}
    assert result["pulled_in"] == []     # b was requested, not pulled in


def test_a_missing_dependency_is_reported_not_fatal(device):
    """The device may not serve every module it names."""
    graph = {"a": ("ghost",)}
    result, _ = _run_deps(device, ["a"], graph)

    assert "a" in result["schemas"]
    assert "ghost" in result["errors"]
    assert result["aborted"] == ""


def test_dependency_following_can_be_turned_off(device):
    graph = {"a": ("b",), "b": ()}
    conn = DependencyConnection(graph)
    with patch("yangstudio.services.netconf.get_session", return_value=conn):
        with patch("yangstudio.services.netconf.close_session"):
            result = netconf.download_schemas(device, ["a"], follow_dependencies=False)
    assert conn.asked == ["a"]
    assert result["pulled_in"] == []


# -- session recovery ------------------------------------------------------

class FlakyConnection:
    """Fails every module once with a dead-session error, then succeeds."""

    def __init__(self):
        self.asked: list[str] = []
        self.failed_once: set[str] = set()

    def get_schema(self, name):
        self.asked.append(name)
        if name not in self.failed_once:
            self.failed_once.add(name)
            from ncclient.transport.errors import SessionCloseError

            raise SessionCloseError(b"")
        return type("Reply", (), {"data": _module(name)})()


def test_a_dropped_session_is_rebuilt_and_the_module_retried(device):
    """A closed session used to poison every module after it."""
    conn = FlakyConnection()
    with patch("yangstudio.services.netconf.get_session", return_value=conn):
        with patch("yangstudio.services.netconf.close_session") as closer:
            result = netconf.download_schemas(
                device, ["a", "b", "c"], follow_dependencies=False
            )

    # Everything succeeds on its retry rather than cascading into failure.
    assert set(result["schemas"]) == {"a", "b", "c"}
    assert result["errors"] == {}
    assert result["aborted"] == ""
    # The dead session is dropped before each retry.
    assert closer.call_count == 3


def test_an_rpc_error_is_not_retried(device):
    """The device answered; reconnecting would change nothing."""
    conn = FakeConnection({"a": _rpc_error("no such schema")})
    with patch("yangstudio.services.netconf.get_session", return_value=conn):
        with patch("yangstudio.services.netconf.close_session") as closer:
            result = netconf.download_schemas(device, ["a"], follow_dependencies=False)

    assert conn.asked == ["a"]          # asked once, not twice
    assert "a" in result["errors"]
    closer.assert_not_called()
