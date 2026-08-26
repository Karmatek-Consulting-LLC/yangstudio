"""Turn a YANG set into a browsable, searchable schema tree.

Node fields keep their RFC 7950 names — ``mandatory``, ``must``, ``when``,
``status``, ``presence``, ``ordered-by`` and the rest are YANG statements, so
they are called what the standard calls them. ``access`` follows pyang's tree
convention of read-write and read-only.

The tree is emitted as plain JSON built for a virtualised client: every node
carries a stable integer ``id`` and children are nested, so the UI can flatten,
filter and window it without a second request.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from pyang import context, repository, statements

from .storage import YangSet

# Statements that carry data (or actions) and therefore belong in the tree.
DATA_KEYWORDS = {
    "container", "list", "leaf", "leaf-list",
    "choice", "case",
    "rpc", "action", "input", "output",
    "notification",
    "anyxml", "anydata",
}

# Which NETCONF-ish edit operations make sense on a node, by access + type.
_RW_OPS = ["get", "get-config", "merge", "replace", "create", "delete", "remove"]
_RO_OPS = ["get"]


class TreeError(Exception):
    """Raised when a set cannot be parsed into a tree."""


@dataclass
class ParseDiagnostic:
    """One error or warning emitted by pyang during validation."""

    level: str          # "error" | "warning"
    module: str
    line: int
    message: str


@dataclass
class ParsedSet:
    """The result of parsing a yangset: trees plus diagnostics."""

    modules: list[dict] = field(default_factory=list)
    diagnostics: list[ParseDiagnostic] = field(default_factory=list)
    node_count: int = 0
    elapsed_ms: int = 0


class _Builder:
    """Walks pyang statements and emits node dictionaries."""

    def __init__(self) -> None:
        self._next_id = 0

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    # -- small helpers -----------------------------------------------------

    @staticmethod
    def _arg(stmt, keyword: str, default: str = "") -> str:
        sub = stmt.search_one(keyword)
        return sub.arg if sub is not None and sub.arg is not None else default

    @staticmethod
    def _module_of(stmt):
        return getattr(stmt, "i_module", None) or getattr(stmt, "i_orig_module", None)

    def _prefix_and_ns(self, stmt) -> tuple[str, str, str]:
        """Return (prefix, namespace, revision) for the statement's module."""
        mod = self._module_of(stmt)
        if mod is None:
            return "", "", ""
        main = getattr(mod, "i_main_module", None) or mod
        prefix = self._arg(main, "prefix")
        namespace = self._arg(main, "namespace")
        revs = [r.arg for r in main.search("revision") if r.arg]
        return prefix, namespace, (max(revs) if revs else "")

    # -- type resolution ---------------------------------------------------

    def _type_data(self, stmt, node: dict) -> None:
        """Fill in datatype, base type, constraints and allowed values."""
        type_stmt = stmt.search_one("type")
        if type_stmt is None:
            return
        node["datatype"] = type_stmt.arg

        # Walk the typedef chain down to a YANG built-in.
        base = type_stmt
        seen = set()
        while getattr(base, "i_typedef", None) is not None:
            typedef = base.i_typedef
            if id(typedef) in seen:      # Defensive: broken circular typedef.
                break
            seen.add(id(typedef))
            nxt = typedef.search_one("type")
            if nxt is None:
                break
            base = nxt
        if base is not type_stmt:
            node["basetype"] = base.arg

        effective = base.arg

        if effective == "enumeration":
            enums = []
            for en in base.search("enum"):
                item = {"name": en.arg}
                value = self._arg(en, "value")
                if value:
                    item["value"] = value
                desc = self._arg(en, "description")
                if desc:
                    item["description"] = desc.strip()
                enums.append(item)
            if enums:
                node["options"] = enums

        elif effective == "identityref":
            bases = [b.arg for b in base.search("base") if b.arg]
            if bases:
                node["identity_bases"] = bases
                node["options"] = [
                    {"name": name} for name in self._derived_identities(base, bases)
                ]

        elif effective == "leafref":
            path = self._arg(base, "path")
            if path:
                node["leafref_path"] = path

        elif effective == "union":
            node["union_types"] = [t.arg for t in base.search("type")]

        elif effective in ("bits",):
            node["options"] = [{"name": b.arg} for b in base.search("bit")]

        # Constraints live on the type statement closest to the leaf.
        for src in (type_stmt, base):
            rng = self._arg(src, "range")
            if rng and "range" not in node:
                node["range"] = rng
            length = self._arg(src, "length")
            if length and "length" not in node:
                node["length"] = length
            patterns = [p.arg for p in src.search("pattern") if p.arg]
            if patterns and "patterns" not in node:
                node["patterns"] = patterns

    def _derived_identities(self, type_stmt, bases: list[str]) -> list[str]:
        """All identities derived from the given bases, transitively.

        Identity hierarchies are often several levels deep (an identityref to
        ``interface-type`` really means the ~280 concrete types deriving from
        ``iana-interface-type`` deriving from it), so a single-level lookup
        would offer the user only an abstract identity they cannot use.
        """
        mod = self._module_of(type_stmt)
        ctx = getattr(mod, "i_ctx", None) if mod is not None else None
        if ctx is None:
            return []

        # Index every identity by bare name -> (qualified name, [base names]).
        index: dict[str, tuple[str, list[str]]] = {}
        for module in ctx.modules.values():
            prefix = self._arg(module, "prefix")
            for identity in module.search("identity"):
                if not identity.arg:
                    continue
                qualified = f"{prefix}:{identity.arg}" if prefix else identity.arg
                parents = [
                    b.arg.split(":")[-1] for b in identity.search("base") if b.arg
                ]
                index[identity.arg] = (qualified, parents)

        # Children-of map, then breadth-first descent from each base.
        children: dict[str, list[str]] = {}
        for name, (_, parents) in index.items():
            for parent in parents:
                children.setdefault(parent, []).append(name)

        found: set[str] = set()
        queue = [b.split(":")[-1] for b in bases]
        seen = set(queue)
        while queue:
            for child in children.get(queue.pop(), []):
                if child in seen:
                    continue          # Guard against a cyclic hierarchy.
                seen.add(child)
                queue.append(child)
                # Only offer identities that are themselves instantiable:
                # keep every derived identity, abstract parents included, but
                # mark leaves first so the UI can prefer them.
                found.add(index[child][0])
        return sorted(found)

    # -- node construction -------------------------------------------------

    def build(self, stmt, parent: dict | None = None) -> dict | None:
        """Recursively build a node dict for ``stmt``, or None if not a data node."""
        if stmt.keyword not in DATA_KEYWORDS:
            return None
        if getattr(stmt, "i_this_not_supported", False):
            return None
        # pyang flags a node whose if-feature evaluated false as
        # i_not_implemented rather than removing it. When a set declares the
        # features a device supports, those nodes are not on that device.
        if getattr(stmt, "i_not_implemented", False):
            return None

        prefix, namespace, revision = self._prefix_and_ns(stmt)
        mod = self._module_of(stmt)
        main = getattr(mod, "i_main_module", None) or mod
        module_name = main.arg if main is not None else ""

        node: dict = {
            "id": self._id(),
            "name": stmt.arg or stmt.keyword,
            "nodetype": stmt.keyword,
            "module": module_name,
            "prefix": prefix,
            "namespace": namespace,
            "revision": revision,
        }

        # Paths. mk_path_str raises on non-data nodes (rpc input/output etc),
        # so fall back to composing from the parent.
        try:
            node["xpath"] = statements.mk_path_str(stmt, False)
            node["xpath_pfx"] = statements.mk_path_str(stmt, True)
        except Exception:
            parent_xpath = parent.get("xpath", "") if parent else ""
            node["xpath"] = f"{parent_xpath}/{stmt.arg}" if stmt.arg else parent_xpath
            parent_pfx = parent.get("xpath_pfx", "") if parent else ""
            node["xpath_pfx"] = (
                f"{parent_pfx}/{prefix}:{stmt.arg}" if stmt.arg else parent_pfx
            )
        node["schema_id"] = node["xpath_pfx"]

        description = self._arg(stmt, "description")
        if description:
            node["description"] = description.strip()

        status = self._arg(stmt, "status")
        if status and status != "current":
            node["status"] = status          # deprecated | obsolete

        if getattr(stmt, "i_not_supported", False):
            node["deviation"] = "not-supported"

        # config-ness determines read-only vs read-write.
        config = getattr(stmt, "i_config", None)
        in_rpc = stmt.keyword in ("rpc", "action", "input", "output")
        if in_rpc or (parent and parent.get("access") == "write"):
            node["access"] = "write"
        elif config is False:
            node["access"] = "read-only"
        else:
            node["access"] = "read-write"

        # Type-specific data.
        if stmt.keyword in ("leaf", "leaf-list"):
            self._type_data(stmt, node)
            default = self._arg(stmt, "default")
            if default:
                node["default"] = default
            units = self._arg(stmt, "units")
            if units:
                node["units"] = units

        if stmt.keyword == "list":
            keys = [k.arg for k in getattr(stmt, "i_key", []) or []]
            if keys:
                node["keys"] = keys
            node["ordered_by"] = self._arg(stmt, "ordered-by", "system")

        if stmt.keyword == "container" and stmt.search_one("presence") is not None:
            node["presence"] = self._arg(stmt, "presence", "true")

        if stmt.keyword in ("list", "leaf-list"):
            min_el = self._arg(stmt, "min-elements")
            max_el = self._arg(stmt, "max-elements")
            if min_el:
                node["min_elements"] = min_el
            if max_el:
                node["max_elements"] = max_el

        # Mandatory-ness.
        if self._arg(stmt, "mandatory") == "true":
            node["mandatory"] = True
        elif stmt.keyword in ("list", "leaf-list"):
            try:
                if int(self._arg(stmt, "min-elements", "0")) > 0:
                    node["mandatory"] = True
            except ValueError:
                pass

        for constraint in ("must", "when"):
            values = [c.arg for c in stmt.search(constraint) if c.arg]
            if values:
                node[constraint] = values

        # Applicable operations.
        if stmt.keyword in ("rpc", "action"):
            node["operations"] = ["rpc"]
        elif stmt.keyword in ("input", "output", "choice", "case"):
            node["operations"] = []
        elif node["access"] == "read-only":
            node["operations"] = _RO_OPS
        elif node["access"] == "write":
            node["operations"] = []
        else:
            node["operations"] = _RW_OPS

        # Recurse.
        children: list[dict] = []
        for child in getattr(stmt, "i_children", []) or []:
            built = self.build(child, parent=node)
            if built is not None:
                children.append(built)
        # rpc input/output are not in i_children on all pyang versions.
        if stmt.keyword in ("rpc", "action"):
            for section in ("input", "output"):
                sub = stmt.search_one(section)
                if sub is not None and not any(c["nodetype"] == section for c in children):
                    built = self.build(sub, parent=node)
                    if built is not None:
                        children.append(built)

        node["children"] = children
        node["has_children"] = bool(children)
        return node


def _diagnostics(ctx) -> list[ParseDiagnostic]:
    """Convert pyang's error tuples into structured diagnostics."""
    from pyang import error as pyang_error

    out: list[ParseDiagnostic] = []
    for pos, tag, args in ctx.errors:
        try:
            message = pyang_error.err_to_str(tag, args)
        except Exception:
            message = str(tag)
        level = "error" if pyang_error.is_error(pyang_error.err_level(tag)) else "warning"
        out.append(
            ParseDiagnostic(
                level=level,
                module=str(getattr(pos, "ref", "")).split("/")[-1],
                line=int(getattr(pos, "line", 0) or 0),
                message=message,
            )
        )
    return out


def parse_yangset(
    yangset: YangSet,
    module_names: list[str] | None = None,
    include_state: bool = True,
) -> ParsedSet:
    """Parse a yangset with pyang and build a tree per requested module.

    ``module_names`` limits which modules get trees built (parsing still needs
    the whole set for imports to resolve). This matters: building trees for
    every module in a large Cisco set is what makes upstream feel slow.
    """
    started = time.monotonic()
    paths = yangset.resolved_paths()
    if not paths:
        raise TreeError(f"yangset {yangset.name!r} resolves to no files")

    # pyang searches a colon-separated path list; give it every directory
    # holding one of our files plus the repo root so imports resolve.
    search_dirs = {str(yangset.repo().path)}
    search_dirs.update(str(p.parent) for p in paths)
    repo = repository.FileRepository(":".join(sorted(search_dirs)))
    ctx = context.Context(repo)
    ctx.opts = _default_opts()

    # Honour the features a device advertises. pyang enables every feature for
    # any module absent from this map, which is what we want for hand-built
    # sets; a device-derived set narrows the tree to what the box implements.
    features = yangset.feature_map()
    if features:
        ctx.features = features

    loaded = []
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        module = ctx.add_module(str(path), text)
        if module is not None:
            loaded.append(module)

    ctx.validate()

    wanted = set(module_names) if module_names else None
    builder = _Builder()
    modules_out: list[dict] = []
    for module in loaded:
        if module.keyword != "module":
            continue  # Submodules are folded into their parent module.
        if wanted is not None and module.arg not in wanted:
            continue

        children: list[dict] = []
        for child in getattr(module, "i_children", []) or []:
            node = builder.build(child)
            if node is None:
                continue
            if not include_state and node.get("access") == "read-only":
                continue
            children.append(node)
        # Top-level rpcs and notifications are not in i_children.
        for keyword in ("rpc", "notification"):
            for stmt in module.search(keyword):
                node = builder.build(stmt)
                if node is not None:
                    children.append(node)

        prefix = builder._arg(module, "prefix")
        namespace = builder._arg(module, "namespace")
        revs = sorted((r.arg for r in module.search("revision") if r.arg), reverse=True)
        modules_out.append(
            {
                "name": module.arg,
                "prefix": prefix,
                "namespace": namespace,
                "revision": revs[0] if revs else "",
                "organization": builder._arg(module, "organization").strip(),
                "description": builder._arg(module, "description").strip(),
                "yang_version": builder._arg(module, "yang-version", "1.0"),
                "children": children,
            }
        )

    modules_out.sort(key=lambda m: m["name"].lower())
    return ParsedSet(
        modules=modules_out,
        diagnostics=_diagnostics(ctx),
        node_count=builder._next_id,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )


def _default_opts():
    """Minimal option object; pyang reads attributes off ctx.opts directly."""
    class Opts:
        # A stand-in for pyang's argparse namespace: it reads these straight off
        # the object, so they are plain attributes rather than fields.
        yang_canonical = False
        yang_remove_unused_imports = False
        trim_yin = False
        lax_quote_checks = True
        lax_xpath_checks = True
        strict = False
        max_line_len = None
        max_identifier_len = None
        features: ClassVar[list] = []
        deviations: ClassVar[list] = []
        keep_comments = False
        no_path_recurse = False
        ignore_errors = True
        ignore_error_tags: ClassVar[list] = []
        verbose = False

    return Opts()


def flatten(modules: list[dict]) -> list[dict]:
    """Depth-first flat list of every node, for search and export."""
    out: list[dict] = []

    def walk(nodes: list[dict], depth: int, module: str) -> None:
        for node in nodes:
            row = {k: v for k, v in node.items() if k != "children"}
            row["depth"] = depth
            row["module"] = node.get("module") or module
            out.append(row)
            walk(node.get("children", []), depth + 1, row["module"])

    for module in modules:
        walk(module.get("children", []), 0, module["name"])
    return out
