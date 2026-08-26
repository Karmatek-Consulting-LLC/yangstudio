"""Tree building: the semantics the whole UI depends on."""
from yangstudio.core.tree import flatten, parse_yangset
from yangstudio.services import explorer


def _index(yangset):
    parsed = parse_yangset(yangset)
    flat = flatten(parsed.modules)
    return parsed, {row["name"]: row for row in flat}, flat


def test_parses_without_errors(repo_with_modules):
    _, yangset = repo_with_modules
    parsed, _, _ = _index(yangset)
    assert [d for d in parsed.diagnostics if d.level == "error"] == []
    assert parsed.modules[0]["name"] == "test-base"
    assert parsed.modules[0]["prefix"] == "tb"


def test_config_vs_state_access(repo_with_modules):
    _, yangset = repo_with_modules
    _, nodes, _ = _index(yangset)
    assert nodes["hostname"]["access"] == "read-write"
    # `config false` must propagate to descendants.
    assert nodes["uptime"]["access"] == "read-only"
    assert nodes["uptime"]["operations"] == ["get"]
    assert "merge" in nodes["hostname"]["operations"]


def test_xpaths_are_prefixed_correctly(repo_with_modules):
    _, yangset = repo_with_modules
    _, nodes, _ = _index(yangset)
    assert nodes["hostname"]["xpath"] == "/config/hostname"
    assert nodes["hostname"]["xpath_pfx"] == "/tb:config/tb:hostname"


def test_typedef_chain_resolves_to_builtin(repo_with_modules):
    _, yangset = repo_with_modules
    _, nodes, _ = _index(yangset)
    load = nodes["load"]
    assert load["datatype"] == "percent"
    assert load["basetype"] == "uint8"
    assert load["range"] == "0..100"


def test_enumeration_options(repo_with_modules):
    _, yangset = repo_with_modules
    _, nodes, _ = _index(yangset)
    options = {o["name"]: o.get("value") for o in nodes["mode"]["options"]}
    assert options == {"fast": "1", "slow": "2"}


def test_identityref_resolves_transitively(repo_with_modules):
    """secure-tcp derives from tcp derives from protocol: all must appear."""
    _, yangset = repo_with_modules
    _, nodes, _ = _index(yangset)
    names = {o["name"].split(":")[-1] for o in nodes["proto"]["options"]}
    assert {"tcp", "secure-tcp"} <= names


def test_list_keys_and_constraints(repo_with_modules):
    _, yangset = repo_with_modules
    _, nodes, _ = _index(yangset)
    assert nodes["peer"]["keys"] == ["id"]
    assert nodes["hostname"]["mandatory"] is True
    assert nodes["hostname"]["length"] == "1..64"
    assert nodes["hostname"]["patterns"] == ["[a-zA-Z0-9-]+"]


def test_rpc_input_output_are_write_access(repo_with_modules):
    _, yangset = repo_with_modules
    _, nodes, _ = _index(yangset)
    assert nodes["reboot"]["nodetype"] == "rpc"
    assert nodes["reboot"]["operations"] == ["rpc"]
    assert nodes["delay"]["access"] == "write"


def test_search_ranks_name_matches_first(repo_with_modules):
    _, yangset = repo_with_modules
    _, _, flat = _index(yangset)
    results = explorer.search(flat, "hostname")
    assert results[0]["name"] == "hostname"


def test_search_filters_by_access_and_nodetype(repo_with_modules):
    _, yangset = repo_with_modules
    _, _, flat = _index(yangset)
    ro = explorer.search(flat, "", access="read-only")
    assert all(r["access"] == "read-only" for r in ro)
    lists = explorer.search(flat, "", nodetypes=["list"])
    assert [r["name"] for r in lists] == ["peer"]


def test_explorer_cache_is_reused(repo_with_modules):
    _, yangset = repo_with_modules
    explorer.invalidate(yangset.slug)
    first, _ = explorer.get_parsed(yangset)
    second, _ = explorer.get_parsed(yangset)
    assert first is second       # Same object: served from cache.
