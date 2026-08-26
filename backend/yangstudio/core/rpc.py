"""Compose NETCONF RPCs from selected schema nodes.

The user picks nodes in the tree, gives values, and picks an operation; this
turns that into the XML that actually goes on the wire. Upstream buries this
behind a grid of form fields — the point here is that the XML is derived
synchronously from the selection so the UI can show it live as you type.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

NETCONF_NS = "urn:ietf:params:xml:ns:netconf:base:1.0"
NETCONF_OPERATION_NS = NETCONF_NS

# Operations that build an <edit-config>, mapped to the nc:operation attribute.
EDIT_OPERATIONS = {
    "merge": "merge",
    "replace": "replace",
    "create": "create",
    "delete": "delete",
    "remove": "remove",
}
READ_OPERATIONS = {"get", "get-config"}


class RpcError(Exception):
    """Raised when a selection cannot be turned into a valid RPC."""


@dataclass
class Selection:
    """One chosen node: where it is, what value it has, what to do with it."""

    xpath: str                      # prefixed data path, e.g. /if:interfaces/if:interface
    value: str = ""
    operation: str = ""             # per-node override of the RPC operation
    nodetype: str = "leaf"
    datatype: str = ""
    is_key: bool = False


@dataclass
class RpcRequest:
    """A full RPC to build."""

    operation: str = "get-config"           # get | get-config | edit-config | rpc
    datastore: str = "running"              # running | candidate | startup
    selections: list[Selection] = field(default_factory=list)
    namespaces: dict[str, str] = field(default_factory=dict)   # prefix -> uri
    message_id: str = "101"
    with_defaults: str = ""                 # report-all | trim | explicit | ...


def _split_step(step: str) -> tuple[str, str]:
    """Split ``pfx:name`` into (prefix, name); prefix may be empty."""
    if ":" in step:
        prefix, name = step.split(":", 1)
        return prefix, name
    return "", step


class _TreeAssembler:
    """Merges a flat list of xpaths into one nested XML subtree."""

    def __init__(self, namespaces: dict[str, str]) -> None:
        self.namespaces = namespaces
        self.roots: list[etree._Element] = []
        # Maps a path tuple to the element created for it, so sibling
        # selections under a shared parent reuse that parent.
        self._nodes: dict[tuple[str, ...], etree._Element] = {}

    def _qname(self, prefix: str, name: str) -> str:
        uri = self.namespaces.get(prefix)
        return f"{{{uri}}}{name}" if uri else name

    def ensure_path(self, xpath: str) -> etree._Element:
        """Create (or fetch) the element chain for ``xpath`` and return its tail."""
        steps = [s for s in xpath.split("/") if s]
        if not steps:
            raise RpcError(f"empty xpath in selection: {xpath!r}")

        current_key: tuple[str, ...] = ()
        parent: etree._Element | None = None
        for step in steps:
            current_key = (*current_key, step)
            existing = self._nodes.get(current_key)
            if existing is not None:
                parent = existing
                continue
            prefix, name = _split_step(step)
            tag = self._qname(prefix, name)
            if parent is None:
                element = etree.Element(tag, nsmap=self._nsmap_for(prefix))
                self.roots.append(element)
            else:
                element = etree.SubElement(parent, tag)
            self._nodes[current_key] = element
            parent = element
        assert parent is not None
        return parent

    def _nsmap_for(self, prefix: str) -> dict:
        uri = self.namespaces.get(prefix)
        return {None: uri} if uri else {}


def build_rpc(request: RpcRequest) -> str:
    """Render ``request`` as a pretty-printed NETCONF RPC document."""
    if not request.selections and request.operation != "get":
        raise RpcError("no nodes selected")

    nsmap = {"nc": NETCONF_NS}
    rpc = etree.Element(f"{{{NETCONF_NS}}}rpc", nsmap=nsmap)
    rpc.set("message-id", request.message_id)

    if request.operation in READ_OPERATIONS:
        _build_read(rpc, request)
    elif request.operation == "edit-config":
        _build_edit(rpc, request)
    elif request.operation == "rpc":
        _build_action(rpc, request)
    else:
        raise RpcError(f"unsupported operation: {request.operation!r}")

    return etree.tostring(rpc, pretty_print=True, encoding="unicode")


def _filter_subtree(parent: etree._Element, request: RpcRequest) -> None:
    """Attach a subtree <filter> built from the selections."""
    assembler = _TreeAssembler(request.namespaces)
    for sel in request.selections:
        element = assembler.ensure_path(sel.xpath)
        # A value on a read is a filter match (e.g. select one interface).
        if sel.value:
            element.text = sel.value
    if not assembler.roots:
        return
    filter_el = etree.SubElement(parent, f"{{{NETCONF_NS}}}filter")
    filter_el.set("type", "subtree")
    for root in assembler.roots:
        filter_el.append(root)


def _build_read(rpc: etree._Element, request: RpcRequest) -> None:
    if request.operation == "get":
        op = etree.SubElement(rpc, f"{{{NETCONF_NS}}}get")
    else:
        op = etree.SubElement(rpc, f"{{{NETCONF_NS}}}get-config")
        source = etree.SubElement(op, f"{{{NETCONF_NS}}}source")
        etree.SubElement(source, f"{{{NETCONF_NS}}}{request.datastore}")
    _filter_subtree(op, request)
    if request.with_defaults:
        wd = etree.SubElement(
            op, "{urn:ietf:params:xml:ns:yang:ietf-netconf-with-defaults}with-defaults"
        )
        wd.text = request.with_defaults


def _build_edit(rpc: etree._Element, request: RpcRequest) -> None:
    edit = etree.SubElement(rpc, f"{{{NETCONF_NS}}}edit-config")
    target = etree.SubElement(edit, f"{{{NETCONF_NS}}}target")
    etree.SubElement(target, f"{{{NETCONF_NS}}}{request.datastore}")

    assembler = _TreeAssembler(request.namespaces)
    for sel in request.selections:
        element = assembler.ensure_path(sel.xpath)
        operation = sel.operation or ""
        if operation and operation in EDIT_OPERATIONS:
            element.set(f"{{{NETCONF_OPERATION_NS}}}operation", EDIT_OPERATIONS[operation])
        # delete/remove target the node itself, so they carry no value.
        if sel.value and operation not in ("delete", "remove"):
            element.text = sel.value

    config = etree.SubElement(edit, f"{{{NETCONF_NS}}}config")
    for root in assembler.roots:
        config.append(root)


def _build_action(rpc: etree._Element, request: RpcRequest) -> None:
    """Build a bare YANG rpc/action invocation."""
    assembler = _TreeAssembler(request.namespaces)
    for sel in request.selections:
        element = assembler.ensure_path(sel.xpath)
        if sel.value:
            element.text = sel.value
    for root in assembler.roots:
        rpc.append(root)
