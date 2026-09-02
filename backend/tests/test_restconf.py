"""RESTCONF URL construction and request planning (RFC 8040)."""
import json

import pytest

from yangstudio.core.resturl import (
    PathNode,
    RestconfError,
    build_body,
    build_path,
    encode_key,
)
from yangstudio.services import restconf

IFACES = PathNode("interfaces", "ietf-interfaces", "container", prefix="if")
IFACE = PathNode("interface", "ietf-interfaces", "list", ["name"], prefix="if")
DESC = PathNode("description", "ietf-interfaces", "leaf", prefix="if")


def _fields(request) -> set[str]:
    """The nodes in a ?fields= query, whatever the separator is encoded as."""
    return set(request.query.removeprefix("fields=").split(restconf.FIELD_SEPARATOR))


def test_first_node_is_qualified_by_module():
    assert build_path([IFACES], {}) == "/restconf/data/ietf-interfaces:interfaces"


def test_later_nodes_in_the_same_module_are_bare():
    assert build_path([IFACES, IFACE], {}) == (
        "/restconf/data/ietf-interfaces:interfaces/interface"
    )


def test_a_module_change_requalifies():
    """An augment from another module announces itself in the path."""
    path = build_path(
        [IFACES, IFACE, PathNode("ipv4", "ietf-ip", "container", prefix="ip"),
         PathNode("mtu", "ietf-ip", "leaf", prefix="ip")],
        {"/if:interfaces/if:interface": {"name": "Gi2"}},
    )
    assert path == "/restconf/data/ietf-interfaces:interfaces/interface=Gi2/ietf-ip:ipv4/mtu"


def test_list_key_goes_into_the_path():
    path = build_path([IFACES, IFACE, DESC], {"/if:interfaces/if:interface": {"name": "Gi1"}})
    assert path.endswith("/interface=Gi1/description")


def test_multiple_keys_are_comma_separated_in_order():
    node = PathNode("entry", "m", "list", ["first", "second"], prefix="m")
    path = build_path(
        [PathNode("top", "m", "container", prefix="m"), node],
        {"/m:top/m:entry": {"second": "b", "first": "a"}},
    )
    assert path.endswith("/entry=a,b")


def test_key_values_are_percent_encoded():
    """Cisco interface names contain slashes, which would break the path."""
    assert encode_key("Gi0/0/1") == "Gi0%2F0%2F1"
    assert encode_key("a,b") == "a%2Cb"
    assert encode_key("plain") == "plain"


def test_empty_path_is_rejected():
    with pytest.raises(RestconfError):
        build_path([], {})


def test_body_names_the_member_with_its_module():
    assert json.loads(build_body(DESC, "uplink")) == {
        "ietf-interfaces:description": "uplink"
    }


@pytest.fixture
def planned(repo_with_modules):
    _, yangset = repo_with_modules

    def run(selections, operation="GET"):
        return restconf.plan(yangset, selections, operation=operation)

    return run


def _sel(xpath, value="", operation="", nodetype="leaf"):
    return {
        "xpath": xpath, "value": value, "operation": operation,
        "nodetype": nodetype, "datatype": "", "is_key": False,
    }


def test_sibling_leaves_fold_into_one_get(planned):
    """Several leaves of one resource is a fields query, not several calls."""
    requests = planned([_sel("/config/hostname"), _sel("/config/load")])
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].path == "/restconf/data/test-base:config"
    assert _fields(requests[0]) == {"hostname", "load"}


def test_a_keyed_leaf_puts_the_key_in_the_url_not_the_fields(planned):
    requests = planned([_sel("/config/peer/id", "p1"), _sel("/config/peer/address")])
    assert len(requests) == 1
    assert requests[0].path.endswith("/peer=p1")
    assert requests[0].query == "fields=address"


def test_an_unvalued_key_stays_a_field(planned):
    """A leaf of a list cannot be fetched on its own — that is a 404."""
    requests = planned([_sel("/config/peer/id"), _sel("/config/peer/address")])
    assert len(requests) == 1
    assert requests[0].path.endswith("/peer")
    assert _fields(requests[0]) == {"id", "address"}


def test_netconf_verbs_map_to_http_methods(planned):
    assert planned([_sel("/config/hostname", "r1")], "merge")[0].method == "PATCH"
    assert planned([_sel("/config/hostname", "r1")], "replace")[0].method == "PUT"
    assert planned([_sel("/config/hostname", "r1")], "delete")[0].method == "DELETE"


def test_per_node_operation_wins(planned):
    """Mirrors NETCONF's nc:operation on an individual node."""
    requests = planned([_sel("/config/hostname", "r1", operation="replace")], "merge")
    assert requests[0].method == "PUT"


def test_a_write_carries_a_json_body(planned):
    request = planned([_sel("/config/hostname", "router-1")], "merge")[0]
    assert request.content_type == "application/yang-data+json"
    assert json.loads(request.body) == {"test-base:hostname": "router-1"}


def test_delete_carries_no_body(planned):
    request = planned([_sel("/config/hostname", "ignored")], "delete")[0]
    assert request.body == ""


def test_unknown_method_is_rejected(planned):
    with pytest.raises(RestconfError, match="not a RESTCONF method"):
        planned([_sel("/config/hostname")], "frobnicate")


def test_empty_selection_is_rejected(planned):
    with pytest.raises(RestconfError, match="no nodes selected"):
        planned([])


def test_unknown_path_is_rejected(planned):
    with pytest.raises(RestconfError, match="not in this set"):
        planned([_sel("/config/nope")])


def test_writing_only_keys_is_rejected(planned):
    """Keys identify the entry; they are not themselves an edit."""
    with pytest.raises(RestconfError, match="only nodes selected are list keys"):
        planned([_sel("/config/peer/id", "p1")], "merge")


def test_two_modules_sharing_a_data_path_resolve_separately(repo_with_modules):
    """ietf-interfaces and openconfig-interfaces both define /interfaces/interface.

    Resolving by plain data path picks whichever was indexed last, so a request
    built from one module's nodes can silently address the other's.
    """
    repo, yangset = repo_with_modules
    (repo.path / "other-base@2024-01-01.yang").write_text(
        """
        module other-base {
          namespace "urn:example:other-base"; prefix ob;
          revision 2024-01-01;
          container config {
            leaf hostname { type string; }
          }
        }
        """
    )
    repo.modules(refresh=True)
    yangset.modules.append({"name": "other-base", "revision": "2024-01-01"})
    yangset.save()
    from yangstudio.services import explorer

    explorer.invalidate(yangset.slug)

    # Same unprefixed path in both modules; the prefix is what separates them.
    ietf = restconf.plan(yangset, [_sel("/tb:config/tb:hostname")])[0]
    other = restconf.plan(yangset, [_sel("/ob:config/ob:hostname")])[0]

    assert ietf.path.startswith("/restconf/data/test-base:config")
    assert other.path.startswith("/restconf/data/other-base:config")
    assert ietf.path != other.path


def test_the_fields_separator_is_percent_encoded(planned):
    """RFC 8040 writes it literally, but a literal ";" is not safe to send.

    A query string may also use ";" where "&" would go, an old W3C
    recommendation some servers still honour. IOS-XE 17.16 does: it splits on
    the literal separator and rejects everything after the first node as an
    unknown query parameter, while 17.3 accepts it. Encoded works on both.
    """
    requests = planned([_sel("/config/hostname"), _sel("/config/load")])
    assert len(requests) == 1
    assert ";" not in requests[0].query
    assert requests[0].query.count("%3B") == 1
    assert _fields(requests[0]) == {"hostname", "load"}
