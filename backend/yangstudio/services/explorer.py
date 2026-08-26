"""Cached parsing and search over YANG sets.

Parsing is the expensive step (seconds to minutes for large sets), so a parse
is done once and held in memory keyed by the set and the modules requested.
Search then runs over a pre-flattened list, which is what lets the UI filter a
100k-node tree without a round trip per keystroke.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from ..core.storage import YangSet
from ..core.tree import ParsedSet, flatten, parse_yangset

# Bound the cache: large sets are memory-hungry (upstream needs ~3.5GB for
# Cisco native models), so hold only a few and evict the oldest.
_MAX_ENTRIES = 6


@dataclass
class _Entry:
    parsed: ParsedSet
    flat: list[dict]
    signature: str


_cache: dict[str, _Entry] = {}
_order: list[str] = []
_lock = threading.Lock()


def _key(yangset: YangSet, modules: list[str] | None) -> str:
    mods = ",".join(sorted(modules)) if modules else "*"
    return f"{yangset.slug}::{mods}"


def _signature(yangset: YangSet) -> str:
    """Changes whenever the set's membership or mtime changes."""
    return f"{yangset.modified}:{len(yangset.modules)}"


def get_parsed(
    yangset: YangSet,
    modules: list[str] | None = None,
    refresh: bool = False,
) -> tuple[ParsedSet, list[dict]]:
    """Parse (or reuse) a yangset, returning the tree and its flat index."""
    key = _key(yangset, modules)
    signature = _signature(yangset)

    with _lock:
        entry = _cache.get(key)
        if entry is not None and entry.signature == signature and not refresh:
            _touch(key)
            return entry.parsed, entry.flat

    # Parse outside the lock: it is slow, and concurrent parses of different
    # sets should not serialise behind each other.
    parsed = parse_yangset(yangset, module_names=modules)
    flat = flatten(parsed.modules)

    with _lock:
        _cache[key] = _Entry(parsed=parsed, flat=flat, signature=signature)
        _touch(key)
        while len(_order) > _MAX_ENTRIES:
            _cache.pop(_order.pop(0), None)
    return parsed, flat


def _touch(key: str) -> None:
    """Mark ``key`` as most recently used. Caller must hold the lock."""
    if key in _order:
        _order.remove(key)
    _order.append(key)


def invalidate(yangset_slug: str) -> None:
    """Drop every cached parse for a set (after its membership changes)."""
    with _lock:
        for key in [k for k in _cache if k.startswith(f"{yangset_slug}::")]:
            _cache.pop(key, None)
            if key in _order:
                _order.remove(key)


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------

_SEARCH_FIELDS = ("name", "xpath", "description", "datatype", "module")


def search(
    flat: list[dict],
    query: str,
    *,
    nodetypes: list[str] | None = None,
    access: str | None = None,
    modules: list[str] | None = None,
    limit: int = 200,
) -> list[dict]:
    """Rank nodes against ``query`` across name, path, description and type.

    Scoring favours name matches over path matches over description matches,
    and exact/prefix hits over substring hits, so typing "description" surfaces
    the leaf named ``description`` rather than the hundreds of nodes whose
    documentation happens to contain the word.
    """
    needle = query.strip().lower()
    type_filter = set(nodetypes) if nodetypes else None
    module_filter = set(modules) if modules else None

    results: list[tuple[int, dict]] = []
    for row in flat:
        if type_filter and row.get("nodetype") not in type_filter:
            continue
        if access and row.get("access") != access:
            continue
        if module_filter and row.get("module") not in module_filter:
            continue

        if not needle:
            results.append((0, row))
            if len(results) >= limit:
                break
            continue

        score = _score(row, needle)
        if score > 0:
            results.append((score, row))

    results.sort(key=lambda pair: (-pair[0], len(pair[1].get("xpath", ""))))
    return [row for _, row in results[:limit]]


def _score(row: dict, needle: str) -> int:
    name = (row.get("name") or "").lower()
    if name == needle:
        return 1000
    if name.startswith(needle):
        return 800
    if needle in name:
        return 600

    xpath = (row.get("xpath") or "").lower()
    if needle in xpath:
        return 400

    datatype = (row.get("datatype") or "").lower()
    if needle in datatype:
        return 200

    description = (row.get("description") or "").lower()
    if needle in description:
        return 100

    module = (row.get("module") or "").lower()
    if needle in module:
        return 50
    return 0


def node_by_xpath(flat: list[dict], xpath: str) -> dict | None:
    """Exact lookup by data path (prefixed or unprefixed)."""
    for row in flat:
        if row.get("xpath") == xpath or row.get("xpath_pfx") == xpath:
            return row
    return None


def stats(parsed: ParsedSet, flat: list[dict]) -> dict:
    """Summary counts used by the explorer header."""
    by_type: dict[str, int] = {}
    by_access: dict[str, int] = {}
    for row in flat:
        by_type[row.get("nodetype", "?")] = by_type.get(row.get("nodetype", "?"), 0) + 1
        by_access[row.get("access", "?")] = by_access.get(row.get("access", "?"), 0) + 1
    return {
        "modules": len(parsed.modules),
        "nodes": len(flat),
        "by_nodetype": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        "by_access": by_access,
        "errors": sum(1 for d in parsed.diagnostics if d.level == "error"),
        "warnings": sum(1 for d in parsed.diagnostics if d.level == "warning"),
        "parse_ms": parsed.elapsed_ms,
    }
