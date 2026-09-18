"""Turn YANG paths into RESTCONF requests (RFC 8040).

The tree is the same one NETCONF addresses; only the encoding differs. Three
rules do most of the work:

* the first node is qualified by its module — ``ietf-interfaces:interfaces``
* later nodes are bare, unless they come from a different module (an augment),
  which re-qualifies them
* a list entry carries its keys in the path — ``interface=GigabitEthernet1``

The awkward part is that key values arrive as separate selections (the user
ticks the key leaf and types a value), so they must be hoisted out of the leaf
list and into the path segment for the list above them.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

# RESTCONF reserves these inside a key value; everything else may stay literal.
# RFC 8040 §3.5.3.1 — "," "/" ":" "=" must be percent-encoded within a key.
_KEY_SAFE = "!$&'()*+;@"


class RestconfError(Exception):
    """Raised when a selection cannot be expressed as a RESTCONF request."""


@dataclass
class RestRequest:
    """One RESTCONF call."""

    method: str
    path: str                       # e.g. /restconf/data/ietf-interfaces:interfaces
    query: str = ""                 # e.g. fields=name%3Bdescription
    body: str = ""
    content_type: str = ""
    # What this request came from, so the UI can tie it back to the tree.
    covers: list[str] = field(default_factory=list)
    # Anything about the selection that RESTCONF cannot express, so it can be
    # said out loud rather than silently dropped.
    notes: list[str] = field(default_factory=list)
    # A single composed write can be aimed at more than one level of the tree:
    # the same change is a small body deep in the URL or a large body high up.
    # ``target`` is the node the body starts at; ``targets`` is every node it
    # could start at instead, outermost first.
    target: str = ""
    targets: list[dict] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{self.path}?{self.query}" if self.query else self.path

    def dict(self) -> dict:
        return {
            "method": self.method,
            "path": self.path,
            "query": self.query,
            "url": self.url,
            "body": self.body,
            "content_type": self.content_type,
            "covers": self.covers,
            "notes": self.notes,
            "target": self.target,
            "targets": self.targets,
        }


def encode_key(value: str) -> str:
    """Percent-encode one list key value for use in a path segment."""
    return quote(value, safe=_KEY_SAFE)


@dataclass
class PathNode:
    """The bits of a tree node the URL builder needs."""

    name: str
    module: str
    nodetype: str
    keys: list[str] = field(default_factory=list)
    # The module prefix, so the builder can address a node the same way the
    # caller does. Two modules can define the same data path, so anything
    # keyed on names alone is ambiguous.
    prefix: str = ""
    # The YANG built-in a leaf's type resolves to, which decides how its value
    # is written in JSON: a uint16 is a number, a uint64 a string, an empty
    # leaf is [null].
    basetype: str = ""
    union_types: list[str] = field(default_factory=list)


def build_path(nodes: list[PathNode], key_values: dict[str, dict[str, str]]) -> str:
    """Render ``/restconf/data/...`` for a resolved chain of nodes.

    ``key_values`` maps a list node's *prefixed* path to ``{key name: value}``.
    """
    if not nodes:
        raise RestconfError("empty path")

    segments: list[str] = []
    previous_module = ""
    walked: list[str] = []

    for node in nodes:
        walked.append(f"{node.prefix}:{node.name}" if node.prefix else node.name)
        # Qualify on the first segment and whenever the module changes: that is
        # how an augment from another module announces itself.
        if node.module and node.module != previous_module:
            segment = f"{node.module}:{node.name}"
        else:
            segment = node.name
        previous_module = node.module or previous_module

        if node.nodetype == "list":
            values = key_values.get("/" + "/".join(walked), {})
            # Keys must appear in their defined order, comma separated.
            ordered = [values.get(k, "") for k in node.keys]
            if any(ordered):
                segment += "=" + ",".join(encode_key(v) for v in ordered)
        segments.append(segment)

    return "/restconf/data/" + "/".join(segments)


# RFC 7951 section 6.1: integers up to 32 bits are JSON numbers. The 64-bit
# ones and decimal64 are strings, because a JSON number cannot be trusted to
# carry them exactly.
_JSON_NUMBER_TYPES = {"int8", "int16", "int32", "uint8", "uint16", "uint32"}
_INTEGER = re.compile(r"^[+-]?\d+$")


def is_empty_leaf(node: PathNode) -> bool:
    """An ``empty`` leaf carries no value: being present is what it says."""
    return node.nodetype == "leaf" and node.basetype == "empty"


def _encode_scalar(node: PathNode, value: str) -> Any:
    text = value.strip()
    basetype = node.basetype
    if basetype == "empty":
        return [None]
    if basetype == "boolean":
        if text.lower() not in ("true", "false"):
            raise RestconfError(
                f"{node.name!r} is a boolean — expected true or false, not {value!r}"
            )
        return text.lower() == "true"
    if basetype in _JSON_NUMBER_TYPES:
        if not _INTEGER.match(text):
            raise RestconfError(
                f"{node.name!r} is {basetype} — {value!r} is not a whole number"
            )
        return int(text)
    # A union is written as whichever member type the value matches. Only the
    # member names are known here, so go by the one case that changes the
    # encoding: something that reads as an integer, in a union that has a small
    # integer member, is a number (a port of 53, not "53").
    small_int_member = _JSON_NUMBER_TYPES.intersection(node.union_types)
    if basetype == "union" and small_int_member and _INTEGER.match(text):
        return int(text)
    return value


def encode_value(node: PathNode, value: str) -> Any:
    """``value`` as it must appear in a JSON body for this node (RFC 7951)."""
    if node.nodetype == "leaf-list":
        # One input box, several entries: a leaf-list is always a JSON array.
        return [_encode_scalar(node, item) for item in value.split(",") if item.strip()]
    return _encode_scalar(node, value)


def member_name(node: PathNode, parent_module: str | None) -> str:
    """The JSON member for ``node``: qualified only where the module changes.

    ``parent_module`` is None for the outermost member of a body, which is
    always qualified — the same rule as the first segment of a URL.
    """
    if node.module and node.module != parent_module:
        return f"{node.module}:{node.name}"
    return node.name


def build_body(leaf: PathNode, value: str) -> str:
    """JSON body for writing a single leaf.

    RESTCONF names the member with the module that defines it, so a PUT to
    .../interface=Gi1/description carries {"ietf-interfaces:description": ...}.
    """
    return json.dumps({member_name(leaf, None): encode_value(leaf, value)}, indent=2)


def _step(node: PathNode) -> str:
    return f"{node.prefix}:{node.name}" if node.prefix else node.name


def build_nested_body(
    chains: list[tuple[list[PathNode], str]],
    start: int,
    key_members: dict[str, dict[str, Any]],
) -> str:
    """One JSON body holding every selection, nested under a shared node.

    ``chains`` pairs each selected node's root-to-node chain with the value
    typed on it; every chain passes through the same node at index ``start``,
    and that node is where the body begins. ``key_members`` maps a list's
    prefixed path to its already-encoded keys, in key order.

    This is the RESTCONF counterpart of a NETCONF edit-config subtree: a device
    validates each request on its own, so an ACL entry sent leaf by leaf is
    rejected at the first leaf for being an incomplete entry. Sent whole, it is
    one valid change.
    """
    body: dict[str, Any] = {}
    for chain, value in chains:
        cursor = body
        walked = [_step(n) for n in chain[:start]]
        for index in range(start, len(chain)):
            node = chain[index]
            walked.append(_step(node))
            parent_module = None if index == start else chain[index - 1].module
            member = member_name(node, parent_module)

            if node.nodetype == "list":
                # A YANG list is a JSON array even with one entry in it. The
                # keys go first: they are what identifies the entry.
                seed = dict(key_members.get("/" + "/".join(walked), {}))
                cursor = cursor.setdefault(member, [seed])[0]
            elif node.nodetype in ("leaf", "leaf-list"):
                parent = chain[index - 1] if index > 0 else None
                is_key = (
                    parent is not None
                    and parent.nodetype == "list"
                    and node.name in parent.keys
                )
                if not is_key:          # Keys were seeded with the entry.
                    cursor[member] = encode_value(node, value)
            else:
                cursor = cursor.setdefault(member, {})
    return json.dumps(body, indent=2)


_ABSOLUTE_URL = re.compile(r"^[a-z][a-z0-9+.-]*://[^/]*(/.*)?$", re.IGNORECASE)


def raw_request(method: str, url: str, body: str = "") -> RestRequest:
    """A hand-written request, checked just enough to be worth sending.

    The URL is a path on the device. A whole URL pasted from another client is
    accepted and reduced to its path — the device and its credentials come from
    the profile, not from whatever host the paste happened to name.
    """
    verb = method.strip().upper()
    if verb not in METHODS:
        raise RestconfError(
            f"{method!r} is not a RESTCONF method — expected one of "
            f"{', '.join(sorted(METHODS))}"
        )

    target = url.strip()
    absolute = _ABSOLUTE_URL.match(target)
    if absolute:
        target = absolute.group(1) or ""
    if not target.startswith("/") or target.startswith("//"):
        raise RestconfError("the URL must be a path on the device, such as /restconf/data/…")
    if any(ch.isspace() for ch in target):
        raise RestconfError("the URL contains whitespace — percent-encode it (a space is %20)")

    path, _, query = target.partition("?")
    text = body.strip()
    if verb in ("GET", "DELETE"):
        text = ""                 # Neither carries a body.
    if text:
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise RestconfError(
                f"the body is not valid JSON — {exc.msg} at line {exc.lineno}, "
                f"column {exc.colno}"
            ) from exc
    return RestRequest(
        method=verb,
        path=path,
        query=query,
        body=text,
        content_type="application/yang-data+json" if text else "",
    )


# HTTP methods, and what they mean against a resource.
METHODS = {
    "GET": "read the resource",
    "PUT": "create or replace the resource",
    "PATCH": "merge into the resource",
    "POST": "create a child of the resource",
    "DELETE": "remove the resource",
}

# NETCONF operations mapped onto their nearest RESTCONF method, so the same
# selection can be sent either way. There is no candidate datastore here, so a
# write lands immediately — an edit-config against candidate is a staged change,
# the PATCH below is not.
FROM_NETCONF = {
    # Top-level operations.
    "get": "GET",
    "get-config": "GET",
    "edit-config": "PATCH",     # merge is edit-config's default operation
    "rpc": "POST",
    # Per-node edit operations.
    "merge": "PATCH",
    "replace": "PUT",
    "create": "POST",
    "delete": "DELETE",
    "remove": "DELETE",
}
