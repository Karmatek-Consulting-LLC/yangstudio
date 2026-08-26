"""RPC construction must produce valid, correctly-namespaced NETCONF."""
import pytest
from lxml import etree

from yangstudio.core.rpc import RpcError, RpcRequest, Selection, build_rpc

NS = {"if": "urn:ietf:params:xml:ns:yang:ietf-interfaces"}
NC = "urn:ietf:params:xml:ns:netconf:base:1.0"


def _parse(xml: str):
    return etree.fromstring(xml.encode())


def test_get_config_builds_subtree_filter():
    xml = build_rpc(
        RpcRequest(
            operation="get-config",
            datastore="running",
            namespaces=NS,
            selections=[Selection(xpath="/if:interfaces/if:interface/if:name")],
        )
    )
    root = _parse(xml)
    assert root.find(f".//{{{NC}}}source/{{{NC}}}running") is not None
    assert root.find(f".//{{{NC}}}filter").get("type") == "subtree"
    assert root.find(".//{urn:ietf:params:xml:ns:yang:ietf-interfaces}name") is not None


def test_siblings_share_one_parent_element():
    """Two leaves under the same list must not duplicate the list element."""
    xml = build_rpc(
        RpcRequest(
            operation="get-config",
            namespaces=NS,
            selections=[
                Selection(xpath="/if:interfaces/if:interface/if:name", value="Gi1"),
                Selection(xpath="/if:interfaces/if:interface/if:description"),
            ],
        )
    )
    root = _parse(xml)
    interfaces = root.findall(".//{urn:ietf:params:xml:ns:yang:ietf-interfaces}interface")
    assert len(interfaces) == 1
    assert {c.tag.split("}")[-1] for c in interfaces[0]} == {"name", "description"}


def test_edit_config_sets_operation_attribute():
    xml = build_rpc(
        RpcRequest(
            operation="edit-config",
            datastore="candidate",
            namespaces=NS,
            selections=[
                Selection(xpath="/if:interfaces/if:interface/if:name", value="Gi1"),
                Selection(
                    xpath="/if:interfaces/if:interface/if:description",
                    value="uplink",
                    operation="merge",
                ),
            ],
        )
    )
    root = _parse(xml)
    assert root.find(f".//{{{NC}}}target/{{{NC}}}candidate") is not None
    desc = root.find(".//{urn:ietf:params:xml:ns:yang:ietf-interfaces}description")
    assert desc.get(f"{{{NC}}}operation") == "merge"
    assert desc.text == "uplink"


def test_delete_carries_no_value():
    xml = build_rpc(
        RpcRequest(
            operation="edit-config",
            namespaces=NS,
            selections=[
                Selection(
                    xpath="/if:interfaces/if:interface/if:description",
                    value="ignored",
                    operation="delete",
                )
            ],
        )
    )
    desc = _parse(xml).find(".//{urn:ietf:params:xml:ns:yang:ietf-interfaces}description")
    assert desc.get(f"{{{NC}}}operation") == "delete"
    assert not desc.text


def test_empty_selection_rejected():
    with pytest.raises(RpcError, match="no nodes selected"):
        build_rpc(RpcRequest(operation="edit-config"))


def test_unknown_operation_rejected():
    with pytest.raises(RpcError, match="unsupported operation"):
        build_rpc(
            RpcRequest(operation="frobnicate", selections=[Selection(xpath="/a")])
        )


# -- datastore operations --------------------------------------------------

def test_commit_needs_no_selection():
    """Many devices refuse a write to running, so commit is the only way to apply."""
    xml = build_rpc(RpcRequest(operation="commit"))
    assert _parse(xml).find(f"{{{NC}}}commit") is not None


def test_confirmed_commit_carries_a_timeout():
    """The safety net for a change that could cut off your own access."""
    root = _parse(build_rpc(RpcRequest(operation="commit", confirmed_timeout=120)))
    commit = root.find(f"{{{NC}}}commit")
    assert commit.find(f"{{{NC}}}confirmed") is not None
    assert commit.find(f"{{{NC}}}confirm-timeout").text == "120"


def test_plain_commit_has_no_confirmed_element():
    commit = _parse(build_rpc(RpcRequest(operation="commit"))).find(f"{{{NC}}}commit")
    assert commit.find(f"{{{NC}}}confirmed") is None


def test_discard_changes():
    assert _parse(build_rpc(RpcRequest(operation="discard-changes"))).find(
        f"{{{NC}}}discard-changes"
    ) is not None


def test_validate_names_its_source_datastore():
    root = _parse(build_rpc(RpcRequest(operation="validate", datastore="candidate")))
    assert root.find(f".//{{{NC}}}validate/{{{NC}}}source/{{{NC}}}candidate") is not None


def test_lock_and_unlock_target_a_datastore():
    for op in ("lock", "unlock"):
        root = _parse(build_rpc(RpcRequest(operation=op, datastore="candidate")))
        assert root.find(f".//{{{NC}}}{op}/{{{NC}}}target/{{{NC}}}candidate") is not None


def test_an_edit_still_requires_a_selection():
    """Only datastore operations are exempt."""
    with pytest.raises(RpcError, match="no nodes selected"):
        build_rpc(RpcRequest(operation="edit-config"))
