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
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from ..core.devices import Device
from ..core.quickparse import dependencies_of
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


# --------------------------------------------------------------------------
# Discovery
#
# The same job the NETCONF service does with <hello> and <get-schema>, done
# over HTTP. It exists for two reasons. Some devices only speak RESTCONF, and
# without this there is no way to get their models at all. On devices that
# speak both it is also the steadier of the two, because every fetch is an
# independent request — there is no session to drop halfway through five
# hundred modules.
# --------------------------------------------------------------------------

# Devices are split between the two versions of the YANG library, and one that
# answers the newer will often 404 the older, so both are tried in turn. Some
# devices answer both, which is why _read_library picks by usefulness rather
# than taking the first that replies.
LIBRARY_PATHS = (
    "/data/ietf-yang-library:yang-library",
    "/data/ietf-yang-library:modules-state",
)

# Schema resources are YANG source rather than JSON, and some devices are
# casual about the content type they put on them.
YANG_ACCEPT = "application/yang, text/plain;q=0.9, */*;q=0.5"

DEFAULT_ROOT = "/restconf"

# A run of failures this long means the device has stopped answering, and
# working through the rest of the queue would only take longer to say so.
MAX_CONSECUTIVE_FAILURES = 5


@dataclass
class _RestFailure:
    """A schema that did not download, and whether retrying could help."""

    message: str
    retryable: bool
    # Set when the device answered. A wall of 404s means something different
    # from a wall of timeouts, and the advice differs with it.
    status: int | None = None


def _client(timeout: float) -> httpx.Client:
    # Lab devices almost always present a self-signed certificate.
    return httpx.Client(verify=False, timeout=timeout, follow_redirects=True)


def _discover_root(client: httpx.Client, device: Device, cfg) -> str:
    """The RESTCONF root, per RFC 8040 section 3.1.

    It is nearly always ``/restconf``, but the standard says to look it up
    rather than assume, and some implementations do put it elsewhere.
    """
    try:
        reply = client.get(
            base_url(device) + "/.well-known/host-meta",
            auth=(cfg.username, cfg.password),
            headers={"Accept": "application/xrd+xml"},
        )
    except httpx.HTTPError:
        return DEFAULT_ROOT
    if reply.is_success and "restconf" in reply.text:
        found = re.search(r"href=['\"]([^'\"]+)['\"]", reply.text)
        if found:
            return found.group(1).rstrip("/") or DEFAULT_ROOT
    return DEFAULT_ROOT


def _text_list(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _names(value) -> list[str]:
    """A list of names, whichever way the library spells it.

    RFC 7895 makes deviations a list of objects carrying a name and revision;
    RFC 8525 makes them a leaf-list of bare module names.
    """
    out = []
    for item in value or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and item.get("name"):
            out.append(str(item["name"]))
    return out


def _schema_url(entry: dict) -> str:
    """Where to download this module's source.

    RFC 7895 calls the leaf ``schema``; RFC 8525 renamed it to ``location``
    and allows several, in which case any of them will do.
    """
    if entry.get("schema"):
        return str(entry["schema"])
    for location in _text_list(entry.get("location")):
        return location
    return ""


def _normalise(entry: dict, conformance: str = "") -> dict:
    """One library entry, in the shape the NETCONF service already returns."""
    return {
        "name": str(entry.get("name", "")),
        "revision": str(entry.get("revision") or ""),
        "namespace": str(entry.get("namespace") or ""),
        "features": _text_list(entry.get("feature")),
        "deviations": _names(entry.get("deviation")),
        "schema": _schema_url(entry),
        "conformance": str(entry.get("conformance-type") or conformance),
    }


def _extract_library(body: dict) -> tuple[list[dict], dict[str, str]]:
    """Modules and submodule schema URLs, from either library format.

    Submodules are kept apart from the module list because nothing selects one
    directly, but a module that includes one will not parse without it, so the
    download still has to be able to find them.
    """
    modules: list[dict] = []
    submodules: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()

    def take(entries, conformance: str = "") -> None:
        for entry in entries or []:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            row = _normalise(entry, conformance)
            key = (row["name"], row["revision"])
            if key in seen:
                continue
            seen.add(key)
            modules.append(row)
            for sub in entry.get("submodule") or []:
                if isinstance(sub, dict) and sub.get("name"):
                    submodules.setdefault(str(sub["name"]), _schema_url(sub))

    library = body.get("ietf-yang-library:yang-library") or body.get("yang-library")
    if isinstance(library, dict):
        for module_set in library.get("module-set") or []:
            if isinstance(module_set, dict):
                take(module_set.get("module"), "implement")
                take(module_set.get("import-only-module"), "import")

    state = body.get("ietf-yang-library:modules-state") or body.get("modules-state")
    if isinstance(state, dict):
        take(state.get("module"))

    modules.sort(key=lambda m: m["name"])
    return modules, submodules


def _read_library(
    client: httpx.Client, device: Device, cfg, root: str
) -> tuple[list[dict], dict[str, str], str]:
    """Fetch the device's YANG library, trying both versions of it.

    Answering is not the same as being useful. A device can serve both
    versions and put download locations in only one of them — IOS-XE behind
    the sandbox gateways does exactly this, publishing an RFC 8525 library
    whose entries carry nothing but a name, namespace and revision, while the
    older RFC 7895 one has a URL for all six hundred modules.

    Taking the first library that returned modules would list everything and
    then be unable to fetch any of it, so both are read and the one that can
    be downloaded from wins. A library with no locations is still returned if
    it is all the device has, because listing the modules is worth something
    on its own.
    """
    listable = None      # modules, but nothing to download them from
    trouble = ""
    for path in LIBRARY_PATHS:
        try:
            reply = client.get(
                f"{base_url(device)}{root}{path}",
                auth=(cfg.username, cfg.password),
                headers={"Accept": ACCEPT},
            )
        except httpx.HTTPError as exc:
            raise RestconfError(
                f"cannot reach RESTCONF on {device.name}: {exc}"
            ) from exc

        if reply.status_code in (401, 403):
            raise RestconfError(
                f"{device.name} rejected the credentials (HTTP "
                f"{reply.status_code}). Check the username and password, and "
                f"that the device has 'ip http authentication local' configured."
            )
        if not reply.is_success:
            trouble = f"HTTP {reply.status_code} from {path}"
            continue
        try:
            body = reply.json()
        except ValueError:
            trouble = f"{path} did not return JSON"
            continue

        modules, submodules = _extract_library(body)
        if not modules:
            trouble = f"{path} returned no modules"
            continue

        source = path.rsplit(":", 1)[-1]
        if any(module["schema"] for module in modules):
            return modules, submodules, source
        if listable is None:
            listable = (modules, submodules, source)

    if listable is not None:
        return listable

    raise RestconfError(
        f"{device.name} did not return a YANG library — {trouble}. RESTCONF "
        f"discovery needs the device to implement ietf-yang-library."
    )


def _restconf_capabilities(
    client: httpx.Client, device: Device, cfg, root: str
) -> list[str]:
    """The device's advertised RESTCONF capabilities, where it publishes them."""
    try:
        reply = client.get(
            f"{base_url(device)}{root}"
            "/data/ietf-restconf-monitoring:restconf-state/capabilities",
            auth=(cfg.username, cfg.password),
            headers={"Accept": ACCEPT},
        )
    except httpx.HTTPError:
        return []
    if not reply.is_success:
        return []
    try:
        body = reply.json()
    except ValueError:
        return []
    state = body.get("ietf-restconf-monitoring:capabilities", body)
    if isinstance(state, dict):
        return _text_list(state.get("capability"))
    return []


def capabilities(device: Device, timeout: float = 60.0) -> dict:
    """What the device supports, read over RESTCONF.

    The return shape deliberately matches the NETCONF service's, so that
    everything downstream — the capability browser, the set builder — does not
    have to care which transport the modules were discovered over.
    """
    cfg = device.resolve("restconf")
    with _client(timeout) as client:
        root = _discover_root(client, device, cfg)
        modules, submodules, source = _read_library(client, device, cfg, root)
        base = _restconf_capabilities(client, device, cfg, root)

    return {
        "session_id": None,
        "transport": "restconf",
        "base_capabilities": base,
        "modules": modules,
        "module_count": len(modules),
        # RESTCONF writes straight to the running datastore (RFC 8040 section
        # 1.4), so the NETCONF datastore capabilities have no equivalent here.
        "supports_candidate": False,
        "supports_startup": False,
        "supports_validate": False,
        "supports_netconf_monitoring": False,
        # Discovery detail, worth having when a device answers but the tree
        # still comes back empty.
        "yang_library": source,
        "restconf_root": root,
        "submodule_count": len(submodules),
        "downloadable": sum(1 for m in modules if m["schema"]),
    }


def _rehome(device: Device, url: str) -> str:
    """Point a schema URL back at the address we actually reached the device on.

    The library fills in the device's own idea of where it lives, which is
    frequently not an address that works from here — a sandbox behind NAT
    advertises its inside address, and a device with several interfaces picks
    whichever one it likes. Only the path is worth keeping.
    """
    if url.startswith(("http://", "https://")):
        parsed = httpx.URL(url)
        path = parsed.raw_path.decode()
    else:
        path = url if url.startswith("/") else "/" + url
    return base_url(device) + path


def _fetch_schema(
    client: httpx.Client, device: Device, cfg, name: str,
    index: dict[str, str], known: set[str],
) -> tuple[str, _RestFailure | None]:
    """One schema download. Returns (text, failure); exactly one is meaningful."""
    url = index.get(name)
    if not url:
        # Being listed and being fetchable are different things, and the
        # difference decides what the user should do about it.
        if name in known:
            return "", _RestFailure(
                f"the device lists {name} but publishes no download URL for "
                f"it — NETCONF can still fetch this module",
                retryable=False,
            )
        return "", _RestFailure(
            f"{name} is not in the device's YANG library", retryable=False
        )

    try:
        reply = client.get(
            _rehome(device, url),
            auth=(cfg.username, cfg.password),
            headers={"Accept": YANG_ACCEPT},
        )
    except httpx.HTTPError as exc:
        return "", _RestFailure(f"{type(exc).__name__}: {exc}", retryable=True)

    if reply.status_code >= 500:
        # The device is struggling rather than refusing; worth another go.
        return "", _RestFailure(
            f"HTTP {reply.status_code} fetching {name}",
            retryable=True, status=reply.status_code,
        )
    if not reply.is_success:
        return "", _RestFailure(
            f"HTTP {reply.status_code} fetching {name}",
            retryable=False, status=reply.status_code,
        )

    text = reply.text
    if not text.lstrip().startswith(("module", "submodule")):
        # Some devices answer 200 with an error document, or with the JSON
        # representation of the node rather than its source.
        return "", _RestFailure(
            f"{name} did not return YANG source", retryable=False
        )
    return text, None


def _why_it_stopped(failures: int, notfound: int, name: str) -> str:
    """Explain a run of failures in terms of what to do about it."""
    if notfound == failures:
        # The library gave us URLs and the device is serving 404 on all of
        # them. A gateway that proxies only /restconf/data does this: the
        # module list is correct, but the source behind it is not exposed.
        return (
            f"stopped after {failures} modules in a row returned HTTP 404. The "
            f"device advertises a download URL for each module but is not "
            f"serving them — a gateway that only proxies /restconf/data will "
            f"do this. The module list is still good; fetch the source over "
            f"NETCONF or from an offline copy of the models."
        )
    return (
        f"stopped after {failures} modules failed in a row at {name!r} — the "
        f"device is not answering"
    )


def download_schemas(
    device: Device,
    module_names: list[str],
    on_progress: Callable[[str, int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    follow_dependencies: bool = True,
    have: set[str] | None = None,
) -> dict:
    """Pull YANG schemas off the device over RESTCONF.

    Same contract as the NETCONF version, including following imports and
    includes as they are discovered, so the two are interchangeable behind the
    download job.

    What is different is that there is no session to keep alive. Each schema is
    an ordinary GET, so a failure is about that one module and the next request
    is unaffected — the cascade that a dropped NETCONF session causes has no
    equivalent here.
    """
    cfg = device.resolve("restconf")
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
    notfound = 0

    with _client(60.0) as client:
        root = _discover_root(client, device, cfg)
        modules, submodules, _ = _read_library(client, device, cfg, root)

        # One place to look up any name the queue produces, modules and
        # submodules alike, plus everything the device mentioned at all so a
        # module with no download URL can be told apart from one it has never
        # heard of.
        index = {m["name"]: m["schema"] for m in modules if m["schema"]}
        known = {m["name"] for m in modules} | set(submodules)
        for sub_name, sub_url in submodules.items():
            if sub_url:
                index.setdefault(sub_name, sub_url)

        if not index:
            raise RestconfError(
                f"{device.name} lists {len(known)} modules but publishes no "
                f"download URL for any of them, so RESTCONF cannot fetch the "
                f"source. Download over NETCONF instead."
            )

        while queue:
            if should_cancel is not None and should_cancel():
                break
            name = queue.pop(0)
            if on_progress is not None:
                on_progress(name, done, done + len(queue) + 1)

            text, failure = _fetch_schema(
                client, device, cfg, name, index, known
            )
            done += 1

            if failure is not None:
                errors[name] = failure.message
                # Any run this long means the rest of the queue will go the
                # same way. Counting only the retryable ones would march
                # through six hundred modules collecting six hundred 404s.
                consecutive_failures += 1
                notfound += 1 if failure.status == 404 else 0
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    aborted = _why_it_stopped(consecutive_failures, notfound, name)
                    break
                continue

            consecutive_failures = 0
            notfound = 0
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
