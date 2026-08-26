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
