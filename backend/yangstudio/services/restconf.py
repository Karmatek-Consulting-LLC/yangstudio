"""RESTCONF: resolve selections into requests, and run them.

The same tree the NETCONF builder addresses, encoded per RFC 8040. Two
differences shape the code:

* RESTCONF addresses one resource per request, where a NETCONF filter can carry
  several branches at once. Several leaves under one parent are folded into a
  single GET with ``?fields=``; anything else becomes its own request.
* There is no candidate datastore. Every write lands immediately, so a
  ``merge`` becomes PATCH and a ``replace`` becomes PUT against live config.
"""
from __future__ import annotations

import json
import time

import httpx

from ..core.devices import Device
from ..core.resturl import (
    FROM_NETCONF,
    METHODS,
    PathNode,
    RestconfError,
    RestRequest,
    build_body,
    build_path,
)
from ..core.storage import YangSet
from . import explorer

ACCEPT = "application/yang-data+json"
CONTENT_TYPE = "application/yang-data+json"


def _index(flat: list[dict]) -> tuple[dict, dict]:
    """Look-up tables from both the plain and prefixed data paths."""
    by_path, by_pfx = {}, {}
    for row in flat:
        by_path[row.get("xpath", "")] = row
        by_pfx[row.get("xpath_pfx", "")] = row
    return by_path, by_pfx


def _chain(row: dict, by_pfx: dict) -> list[PathNode]:
    """Every node from the module root down to ``row``.

    Walks the *prefixed* path. Two modules can define the same data path —
    ietf-interfaces and openconfig-interfaces both have /interfaces/interface —
    so resolving by plain path silently picks whichever was indexed last, and
    the request goes to the wrong model.
    """
    parts = [p for p in row.get("xpath_pfx", "").split("/") if p]
    nodes: list[PathNode] = []
    for depth in range(1, len(parts) + 1):
        path = "/" + "/".join(parts[:depth])
        ancestor = by_pfx.get(path)
        if ancestor is None:
            raise RestconfError(f"no node at {path!r} in this set")
        nodes.append(
            PathNode(
                name=ancestor["name"],
                module=ancestor.get("module", ""),
                nodetype=ancestor.get("nodetype", ""),
                keys=list(ancestor.get("keys") or []),
                prefix=ancestor.get("prefix", ""),
            )
        )
    return nodes


def _collect_key_values(selections: list[dict], by_path: dict, by_pfx: dict) -> dict:
    """Hoist values typed on key leaves up to the list entry they identify.

    Keyed by prefixed path, for the same reason as _chain.
    """
    keys: dict[str, dict[str, str]] = {}
    for selection in selections:
        value = (selection.get("value") or "").strip()
        if not value:
            continue
        row = by_pfx.get(selection.get("xpath", "")) or by_path.get(selection.get("xpath", ""))
        if row is None:
            continue
        parent_path = row.get("xpath_pfx", "").rsplit("/", 1)[0]
        parent = by_pfx.get(parent_path)
        if parent is None or parent.get("nodetype") != "list":
            continue
        if row["name"] in (parent.get("keys") or []):
            keys.setdefault(parent_path, {})[row["name"]] = value
    return keys


def plan(
    yangset: YangSet,
    selections: list[dict],
    operation: str = "GET",
    modules: list[str] | None = None,
) -> list[RestRequest]:
    """Turn selections into the RESTCONF calls that express them."""
    if not selections:
        raise RestconfError("no nodes selected")

    _, flat = explorer.get_parsed(yangset, modules, False)
    by_path, by_pfx = _index(flat)
    key_values = _collect_key_values(selections, by_path, by_pfx)

    # NETCONF edit verbs arrive lowercase ("merge"); map before upper-casing,
    # or "merge" becomes the non-existent HTTP method "MERGE".
    method = FROM_NETCONF.get(operation.strip().lower(), operation.strip().upper())
    if method not in METHODS:
        raise RestconfError(
            f"{operation!r} is not a RESTCONF method — expected one of "
            f"{', '.join(sorted(METHODS))}"
        )

    resolved: list[tuple[dict, dict, list[PathNode]]] = []
    for selection in selections:
        row = by_pfx.get(selection.get("xpath", "")) or by_path.get(selection.get("xpath", ""))
        if row is None:
            raise RestconfError(f"{selection.get('xpath')!r} is not in this set")
        resolved.append((selection, row, _chain(row, by_pfx)))

    if method == "GET":
        return _plan_reads(resolved, by_pfx, key_values)
    return _plan_writes(resolved, key_values, method)


def _plan_reads(resolved, by_pfx: dict, key_values: dict) -> list[RestRequest]:
    """Fold sibling leaves into one GET with ?fields=, keep the rest separate."""
    groups: dict[str, list] = {}
    standalone: list = []

    for _selection, row, chain in resolved:
        parent_path = row.get("xpath_pfx", "").rsplit("/", 1)[0]
        parent = by_pfx.get(parent_path)
        is_leaf = row.get("nodetype") in ("leaf", "leaf-list")
        is_key = parent is not None and row["name"] in (parent.get("keys") or [])

        # A key whose value pins the entry is already in the URL, so asking for
        # it again is noise. A key with no value is an ordinary field — and it
        # must not become its own request, because a leaf of a list cannot be
        # fetched without saying which entry (that is a 404).
        if is_key and row["name"] in key_values.get(parent_path, {}):
            continue
        if is_leaf and parent is not None:
            groups.setdefault(parent_path, []).append((row, chain))
        else:
            standalone.append((row, chain))

    requests: list[RestRequest] = []
    for _parent_path, members in groups.items():
        parent_chain = members[0][1][:-1]
        if not parent_chain:
            standalone.extend(members)
            continue
        path = build_path(parent_chain, key_values)
        fields = ";".join(dict.fromkeys(row["name"] for row, _ in members))
        requests.append(
            RestRequest(
                method="GET",
                path=path,
                query=f"fields={fields}",
                covers=[row["xpath_pfx"] for row, _ in members],
            )
        )

    for row, chain in standalone:
        requests.append(
            RestRequest(method="GET", path=build_path(chain, key_values), covers=[row["xpath_pfx"]])
        )
    return requests


def _plan_writes(resolved, key_values: dict, method: str) -> list[RestRequest]:
    """One request per node — RESTCONF has no multi-branch edit."""
    requests: list[RestRequest] = []
    for selection, row, chain in resolved:
        parent_keys = key_values.get(row.get("xpath_pfx", "").rsplit("/", 1)[0], {})
        # A key leaf identifies the entry; it is not itself edited.
        if row["name"] in parent_keys:
            continue
        # A per-node operation wins, mirroring NETCONF's nc:operation.
        own = (selection.get("operation") or "").strip().lower()
        node_method = FROM_NETCONF.get(own, own.upper()) if own else method
        if node_method not in METHODS:
            node_method = method

        body = ""
        content_type = ""
        if node_method in ("PUT", "PATCH", "POST") and selection.get("value"):
            body = build_body(chain[-1], selection["value"])
            content_type = CONTENT_TYPE
        requests.append(
            RestRequest(
                method=node_method,
                path=build_path(chain, key_values),
                body=body,
                content_type=content_type,
                covers=[row["xpath_pfx"]],
            )
        )
    if not requests:
        raise RestconfError(
            "nothing to write — the only nodes selected are list keys, which "
            "identify the entry rather than being edited"
        )
    return requests


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------

def base_url(device: Device) -> str:
    cfg = device.resolve("restconf")
    if not cfg.address:
        raise RestconfError(f"device {device.name!r} has no address")
    return f"https://{cfg.address}:{cfg.port}"


def run(device: Device, request: RestRequest, timeout: float = 60.0) -> dict:
    """Execute one RESTCONF call."""
    cfg = device.resolve("restconf")
    headers = {"Accept": ACCEPT}
    if request.content_type:
        headers["Content-Type"] = request.content_type

    started = time.monotonic()
    try:
        # Lab devices almost always present a self-signed certificate.
        with httpx.Client(verify=False, timeout=timeout, follow_redirects=True) as client:
            response = client.request(
                request.method,
                base_url(device) + request.url,
                auth=(cfg.username, cfg.password),
                headers=headers,
                content=request.body or None,
            )
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "status": 0,
            "error": {"message": f"{type(exc).__name__}: {exc}"},
        }

    elapsed = int((time.monotonic() - started) * 1000)
    text = response.text
    pretty = text
    if text and "json" in response.headers.get("content-type", ""):
        try:
            pretty = json.dumps(response.json(), indent=2)
        except ValueError:
            pretty = text

    return {
        "ok": response.is_success,
        "status": response.status_code,
        "reason": response.reason_phrase,
        "elapsed_ms": elapsed,
        "reply": pretty,
        "content_type": response.headers.get("content-type", ""),
    }


def probe(device: Device, timeout: float = 20.0) -> dict:
    """Check RESTCONF is reachable and report the root and YANG library."""
    cfg = device.resolve("restconf")
    try:
        with httpx.Client(verify=False, timeout=timeout, follow_redirects=True) as client:
            well_known = client.get(
                base_url(device) + "/.well-known/host-meta",
                auth=(cfg.username, cfg.password),
                headers={"Accept": "application/xrd+xml"},
            )
            root = "/restconf"
            if well_known.is_success and "restconf" in well_known.text:
                # <Link rel='restconf' href='/restconf'/>
                import re

                found = re.search(r"href=['\"]([^'\"]+)['\"]", well_known.text)
                if found:
                    root = found.group(1)

            caps = client.get(
                f"{base_url(device)}{root}/data/ietf-restconf-monitoring:restconf-state/capabilities",
                auth=(cfg.username, cfg.password),
                headers={"Accept": ACCEPT},
            )
    except httpx.HTTPError as exc:
        raise RestconfError(f"cannot reach RESTCONF on {device.name}: {exc}") from exc

    capabilities: list[str] = []
    if caps.is_success:
        try:
            body = caps.json()
            state = body.get("ietf-restconf-monitoring:capabilities", body)
            capabilities = list(state.get("capability", []))
        except ValueError:
            pass

    return {
        "reachable": well_known.is_success or caps.is_success,
        "root": root,
        "well_known_status": well_known.status_code,
        "capabilities": capabilities,
        "base_url": base_url(device),
    }
