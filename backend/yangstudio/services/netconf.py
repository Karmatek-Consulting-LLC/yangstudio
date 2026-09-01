"""NETCONF sessions, capabilities, schema download, and RPC execution.

ncclient is blocking, so every entry point here is designed to be called from
a thread (FastAPI's ``run_in_threadpool``). Sessions are cached per device so
that repeated operations reuse one SSH channel — reconnecting per RPC is a
large part of why the upstream UI feels sluggish.
"""
from __future__ import annotations

import contextlib
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from ncclient import manager
from ncclient.operations import RPCError
from ncclient.operations.errors import TimeoutExpiredError
from ncclient.transport.errors import (
    AuthenticationError,
    SessionCloseError,
    SSHError,
    TransportError,
)

from ..core.devices import Device
from ..core.quickparse import dependencies_of

# Cisco platforms want specific ncclient device handlers.
_HANDLERS = {
    "iosxe": "iosxe",
    "iosxr": "iosxr",
    "nxos": "nexus",
    "junos": "junos",
    "generic": "default",
}


class NetconfError(Exception):
    """Any failure reaching or talking to a device."""


@dataclass
class _Session:
    connection: object
    opened: float


_sessions: dict[str, _Session] = {}
_lock = threading.Lock()


# An individual RPC should not be able to hang a worker indefinitely. Cisco
# get-schema on a big native model is slow but not this slow.
RPC_TIMEOUT = int(os.environ.get("YANGSTUDIO_RPC_TIMEOUT", "60"))

# If this many RPCs fail back to back, the session is gone — stop rather than
# grinding through hundreds more at RPC_TIMEOUT each.
MAX_CONSECUTIVE_FAILURES = 5


def _connect(device: Device):
    cfg = device.resolve("netconf")
    if not cfg.address:
        raise NetconfError(f"device {device.name!r} has no address")
    handler = _HANDLERS.get(cfg.device_variant, "default")
    try:
        return manager.connect(
            host=cfg.address,
            port=cfg.port,
            username=cfg.username,
            password=cfg.password,
            hostkey_verify=False,
            allow_agent=False,
            look_for_keys=False,
            device_params={"name": handler},
            timeout=30,
            manager_params={"timeout": RPC_TIMEOUT},
        )
    except AuthenticationError as exc:
        raise NetconfError(
            f"Authentication failed for {device.name}. Check the username and "
            f"password on the device profile."
        ) from exc
    except SessionCloseError as exc:
        # SSH and the netconf subsystem both succeeded, then the device hung up
        # before sending its <hello>. That is almost never a credential problem
        # — it is the device declining to authorize the NETCONF session.
        raise NetconfError(
            f"{device.name} accepted the SSH login and opened the NETCONF "
            f"subsystem, then closed the session without sending its hello.\n\n"
            f"This is a device-side authorization problem, not a credential one. "
            f"On Cisco IOS-XE, NETCONF needs AAA configured:\n"
            f"    aaa new-model\n"
            f"    aaa authentication login default local\n"
            f"    aaa authorization exec default local\n\n"
            f"Also confirm the account has privilege 15, and that "
            f"'show platform software yang-management process' reports dmiauthd "
            f"as Running."
        ) from exc
    except SSHError as exc:
        raise NetconfError(f"cannot reach {cfg.address}:{cfg.port}: {exc}") from exc
    except EOFError as exc:
        # The transport closed mid-handshake with nothing to say — a bare
        # EOFError, no message. The port is open and something is listening,
        # but it refused to go further. A RESTCONF-only account on a sandbox
        # behaves exactly like this.
        raise NetconfError(
            f"{cfg.address}:{cfg.port} closed the connection during the SSH "
            f"handshake, without saying why.\n\n"
            f"The port is open, so something is listening, but the session was "
            f"refused before NETCONF began. Usually the account cannot log in "
            f"over SSH at all — sandbox credentials are often issued for "
            f"RESTCONF only — or the port forwards somewhere that is not a "
            f"NETCONF server. Check that {cfg.username!r} can SSH to the "
            f"device, and try RESTCONF if it cannot."
        ) from exc
    except Exception as exc:                       # ncclient raises broadly
        # Some of these arrive with an empty str(), which would otherwise end
        # the sentence on a colon and tell the reader nothing.
        detail = str(exc) or type(exc).__name__
        raise NetconfError(f"connection to {device.name} failed: {detail}") from exc


def get_session(device: Device, reuse: bool = True):
    """Return a live ncclient manager for ``device``, reconnecting if stale."""
    with _lock:
        cached = _sessions.get(device.slug)
        if reuse and cached is not None:
            try:
                if cached.connection.connected:
                    return cached.connection
            except Exception:
                pass  # Fall through and rebuild the session.
            _sessions.pop(device.slug, None)

    # Connect outside the lock: the SSH and NETCONF handshake takes seconds,
    # and holding a process-wide lock across it serialises every other device.
    connection = _connect(device)
    with _lock:
        existing = _sessions.get(device.slug)
        if reuse and existing is not None:
            # Another thread won the race; keep theirs and drop ours.
            with contextlib.suppress(Exception):
                connection.close_session()
            return existing.connection
        _sessions[device.slug] = _Session(connection=connection, opened=time.time())
    return connection


def close_session(device_slug: str) -> bool:
    """Tear down a cached session. Returns True if one was open."""
    with _lock:
        session = _sessions.pop(device_slug, None)
    if session is None:
        return False
    # The device may already have dropped the channel; nothing to do if so.
    with contextlib.suppress(Exception):
        session.connection.close_session()
    return True


def capabilities(device: Device) -> dict:
    """Connect and report what the device supports."""
    connection = get_session(device)
    try:
        caps = sorted(str(c) for c in connection.server_capabilities)
    except TRANSPORT_FAILURES as exc:
        raise NetconfError(_drop_session(device, exc)) from exc

    # Split the YANG modules advertised via capability URIs from base caps.
    modules, base = [], []
    for cap in caps:
        if "module=" in cap:
            params = dict(
                part.split("=", 1)
                for part in cap.split("?", 1)[-1].split("&")
                if "=" in part
            )
            modules.append(
                {
                    "name": params.get("module", ""),
                    "revision": params.get("revision", ""),
                    "features": [f for f in params.get("features", "").split(",") if f],
                    "deviations": [d for d in params.get("deviations", "").split(",") if d],
                }
            )
        else:
            base.append(cap)

    modules.sort(key=lambda m: m["name"])
    return {
        "session_id": getattr(connection, "session_id", None),
        "base_capabilities": base,
        "modules": modules,
        "module_count": len(modules),
        "supports_candidate": any(":candidate" in c for c in base),
        "supports_startup": any(":startup" in c for c in base),
        "supports_validate": any(":validate" in c for c in base),
        "supports_netconf_monitoring" : any("ietf-netconf-monitoring" in c for c in caps),
    }


def download_schemas(
    device: Device,
    module_names: list[str],
    on_progress: Callable[[str, int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    follow_dependencies: bool = True,
    have: set[str] | None = None,
) -> dict:
    """Pull YANG schemas off the device via <get-schema>.

    Each module is a separate round trip (~1s against real hardware), so this
    reports progress per module and checks for cancellation between them.

    Two things make it more than a loop:

    *Dependencies are followed.* A module that imports another is useless
    without it — the set will not parse — so each downloaded module is scanned
    for its imports and includes, and anything not already present is queued.
    The queue grows as it runs, the way a package manager resolves a tree.

    *A dropped session is rebuilt.* Devices close NETCONF sessions for their
    own reasons, and once one closes every later request on it fails too.
    Rather than letting that cascade, a transport failure reconnects and
    retries the module once.
    """
    results: dict[str, str] = {}
    errors: dict[str, str] = {}
    pulled_in: list[str] = []
    aborted = ""

    queue = list(dict.fromkeys(module_names))     # de-duplicate, keep order
    requested = set(queue)
    # Modules already in the repository do not need fetching again.
    seen = set(queue) | (have or set())
    done = 0
    consecutive_failures = 0

    connection = get_session(device)

    while queue:
        if should_cancel is not None and should_cancel():
            break
        name = queue.pop(0)
        if on_progress is not None:
            on_progress(name, done, done + len(queue) + 1)

        text, failure = _fetch_schema(device, connection, name)
        if failure is not None and failure.retryable:
            # The session is gone; a fresh one usually works.
            close_session(device.slug)
            connection = get_session(device, reuse=False)
            text, failure = _fetch_schema(device, connection, name)

        done += 1

        if failure is not None:
            errors[name] = failure.message
            if failure.retryable:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    aborted = (
                        f"stopped after {consecutive_failures} modules failed in a "
                        f"row at {name!r} — the device is not answering"
                    )
                    close_session(device.slug)
                    break
            continue

        consecutive_failures = 0
        results[name] = text

        if follow_dependencies:
            for dep in dependencies_of(text):
                if dep in seen:
                    continue
                seen.add(dep)
                queue.append(dep)
                if dep not in requested:
                    pulled_in.append(dep)

    return {
        "schemas": results,
        "errors": errors,
        "aborted": aborted,
        # Which modules were added because something else imported them.
        "pulled_in": sorted(pulled_in),
    }


@dataclass
class _Failure:
    message: str
    retryable: bool


def _fetch_schema(device: Device, connection, name: str) -> tuple[str, _Failure | None]:
    """One <get-schema>. Returns (text, failure); exactly one is meaningful."""
    try:
        reply = connection.get_schema(name)
        # ncclient returns the schema wrapped in an RPC reply.
        data = getattr(reply, "data", None)
        return (data if isinstance(data, str) else str(reply)), None
    except RPCError as exc:
        # The device answered and said no — that is about this module, not the
        # session, so reconnecting would not help.
        return "", _Failure(str(exc), retryable=False)
    except TRANSPORT_FAILURES as exc:
        return "", _Failure(f"{type(exc).__name__}: {exc}", retryable=True)
    except Exception as exc:
        return "", _Failure(f"{type(exc).__name__}: {exc}", retryable=True)


# Failures that mean the session itself is unusable, as opposed to the device
# answering with an error. After one of these the channel may be desynchronised
# — a late reply arriving against a message-id we have moved past makes every
# subsequent RPC time out — so the session must be dropped, not reused.
TRANSPORT_FAILURES = (TimeoutExpiredError, SessionCloseError, TransportError, OSError, EOFError)


def _drop_session(device: Device, exc: Exception) -> str:
    """Discard a broken session and explain what happened."""
    close_session(device.slug)
    if isinstance(exc, TimeoutExpiredError):
        return (
            f"{device.name} did not reply within {RPC_TIMEOUT}s. The session has "
            f"been closed — try again and it will reconnect. If it keeps timing "
            f"out, the request may be returning more data than the device can "
            f"produce quickly; narrow the selection."
        )
    return (
        f"The NETCONF session to {device.name} failed ({type(exc).__name__}: {exc}). "
        f"It has been closed — try again and it will reconnect."
    )


def run_rpc(device: Device, rpc_xml: str) -> dict:
    """Dispatch a raw RPC document and return the reply plus timing."""
    connection = get_session(device)
    started = time.monotonic()
    try:
        reply = connection.dispatch(_to_element(rpc_xml))
        elapsed = int((time.monotonic() - started) * 1000)
        raw = str(reply)
        return {
            "ok": True,
            "elapsed_ms": elapsed,
            "reply": prettify(raw),
            "raw_bytes": len(raw),
        }
    except RPCError as exc:
        # The device answered and said no. The session is fine; keep it.
        return {
            "ok": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": {
                "type": getattr(exc, "type", ""),
                "tag": getattr(exc, "tag", ""),
                "severity": getattr(exc, "severity", ""),
                "path": getattr(exc, "path", ""),
                "message": getattr(exc, "message", "") or str(exc),
                "info": getattr(exc, "info", ""),
            },
        }
    except TRANSPORT_FAILURES as exc:
        return {
            "ok": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "session_reset": True,
            "error": {"message": _drop_session(device, exc)},
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": {"message": f"{type(exc).__name__}: {exc}"},
        }


# Pretty-printing a very large reply is slow and the browser will not render
# it usefully either. Past this, hand back the original text.
MAX_PRETTY_BYTES = 4 * 1024 * 1024


def prettify(xml_text: str) -> str:
    """Re-indent an XML document. Returns the input unchanged if it will not parse.

    Devices send replies as one long line — correct on the wire, unreadable on
    screen. lxml can only re-indent when it drops the existing whitespace, so
    the text is reparsed with a blank-text-stripping parser first.
    """
    if not xml_text or len(xml_text) > MAX_PRETTY_BYTES:
        return xml_text
    from lxml import etree

    try:
        parser = etree.XMLParser(remove_blank_text=True, recover=True, huge_tree=True)
        root = etree.fromstring(xml_text.encode(), parser=parser)
        if root is None:
            return xml_text
        return etree.tostring(root, pretty_print=True, encoding="unicode")
    except Exception:
        return xml_text        # Not XML, or malformed: show what arrived.


def _to_element(rpc_xml: str):
    """Strip the outer <rpc> envelope; ncclient adds its own."""
    from lxml import etree

    root = etree.fromstring(rpc_xml.encode())
    if etree.QName(root).localname == "rpc":
        children = [c for c in root if isinstance(c.tag, str)]
        if len(children) == 1:
            return children[0]
    return root


def datastores(device: Device) -> list[str]:
    """Which datastores this device will accept as a target."""
    caps = capabilities(device)
    stores = ["running"]
    if caps["supports_candidate"]:
        stores.append("candidate")
    if caps["supports_startup"]:
        stores.append("startup")
    return stores
