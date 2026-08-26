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
from dataclasses import dataclass, field
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
    query: str = ""                 # e.g. fields=name;description
    body: str = ""
    content_type: str = ""
    # What this request came from, so the UI can tie it back to the tree.
    covers: list[str] = field(default_factory=list)

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


def build_path(nodes: list[PathNode], key_values: dict[str, dict[str, str]]) -> str:
    """Render ``/restconf/data/...`` for a resolved chain of nodes.

    ``key_values`` maps a list node's data path to ``{key name: value}``.
    """
    if not nodes:
        raise RestconfError("empty path")

    segments: list[str] = []
    previous_module = ""
    walked: list[str] = []

    for node in nodes:
        walked.append(node.name)
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


def build_body(leaf: PathNode, value: str) -> str:
    """JSON body for writing a single leaf.

    RESTCONF names the member with the module that defines it, so a PUT to
    .../interface=Gi1/description carries {"ietf-interfaces:description": ...}.
    """
    member = f"{leaf.module}:{leaf.name}" if leaf.module else leaf.name
    return json.dumps({member: value}, indent=2)


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
