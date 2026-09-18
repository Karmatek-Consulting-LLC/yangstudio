"""Composing one RESTCONF write from many selections, and sending one by hand.

The shape under test is a real one: an IOS-XE extended access list. The entry
is a list inside a list, grafted into another module's tree, with an `empty`
leaf and a union-typed port — and the device will only take it whole.
"""
import json
import textwrap

import pytest

from yangstudio.core.resturl import PathNode, RestconfError, build_body, encode_value, raw_request
from yangstudio.services import explorer, restconf

NATIVE = textwrap.dedent(
    """
    module test-native {
      yang-version 1.1;
      namespace "urn:example:test-native";
      prefix ios;
      revision 2024-01-01;

      container native {
        leaf hostname { type string; }
        container ip {
          container access-list { description "Filled in by test-acl."; }
        }
        container vlan { description "Filled in by test-acl too."; }
      }
      leaf motd { type string; }
    }
    """
)

ACL = textwrap.dedent(
    """
    module test-acl {
      yang-version 1.1;
      namespace "urn:example:test-acl";
      prefix acl;
      import test-native { prefix ios; }
      revision 2024-01-01;

      augment "/ios:native/ios:ip/ios:access-list" {
        list extended {
          key "name";
          leaf name { type string; }
          list access-list-seq-rule {
            key "sequence";
            leaf sequence { type uint32; }
            container ace-rule {
              leaf action { type enumeration { enum permit; enum deny; } }
              leaf protocol { type string; }
              // As on IOS-XE, the address and port forms are choices. A choice
              // is schema only: it must not show up in a URL or a body.
              choice source-choice {
                case ipv4-address-case {
                  leaf ipv4-address { type string; }
                  leaf mask { type string; }
                }
                case any-case { leaf any { type empty; } }
              }
              choice destination-choice {
                case dst-any-case { leaf dst-any { type empty; } }
                case dst-host-case { leaf dst-host { type string; } }
              }
              choice dst-port-choice {
                case dst-eq-case {
                  leaf dst-eq {
                    type union {
                      type uint16;
                      type enumeration { enum domain; enum www; }
                    }
                  }
                }
              }
              leaf log { type boolean; }
              leaf big { type uint64; }
              leaf-list tag { type uint8; }
            }
          }
        }
      }
    }
    """
)

EXT = "/ios:native/ios:ip/ios:access-list/acl:extended"
RULE = f"{EXT}/acl:access-list-seq-rule"
ACE = f"{RULE}/acl:ace-rule"


def _sel(xpath, value="", operation="", nodetype="leaf"):
    return {
        "xpath": xpath, "value": value, "operation": operation,
        "nodetype": nodetype, "datatype": "", "is_key": False,
    }


@pytest.fixture
def acl(repo_with_modules):
    repo, yangset = repo_with_modules
    (repo.path / "test-native@2024-01-01.yang").write_text(NATIVE)
    (repo.path / "test-acl@2024-01-01.yang").write_text(ACL)
    repo.modules(refresh=True)
    yangset.modules += [
        {"name": "test-native", "revision": "2024-01-01"},
        {"name": "test-acl", "revision": "2024-01-01"},
    ]
    yangset.save()
    explorer.invalidate(yangset.slug)

    def run(selections, operation="POST", compose="single", target=""):
        return restconf.plan(
            yangset, selections, operation=operation, compose=compose, target=target
        )

    return run


def _the_acl():
    return [
        _sel(f"{EXT}/acl:name", "MS_Access_List_Extended"),
        _sel(f"{RULE}/acl:sequence", "2"),
        _sel(f"{ACE}/acl:action", "permit"),
        _sel(f"{ACE}/acl:protocol", "udp"),
        _sel(f"{ACE}/acl:ipv4-address", "172.16.5.0"),
        _sel(f"{ACE}/acl:mask", "0.0.0.255"),
        _sel(f"{ACE}/acl:dst-any"),
        _sel(f"{ACE}/acl:dst-eq", "53"),
    ]


# -- the request the feature exists for ------------------------------------


def test_an_access_list_entry_is_one_post_to_its_parent(acl):
    requests = acl(_the_acl(), "POST")

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    # POST creates a child, so it is aimed at the parent of what is created.
    assert request.path == "/restconf/data/test-native:native/ip/access-list"
    assert json.loads(request.body) == {
        "test-acl:extended": [
            {
                "name": "MS_Access_List_Extended",
                "access-list-seq-rule": [
                    {
                        "sequence": 2,
                        "ace-rule": {
                            "action": "permit",
                            "protocol": "udp",
                            "ipv4-address": "172.16.5.0",
                            "mask": "0.0.0.255",
                            "dst-any": [None],
                            "dst-eq": 53,
                        },
                    }
                ],
            }
        ]
    }
    assert request.content_type == "application/yang-data+json"
    assert len(request.covers) == 8


def test_patch_and_put_address_the_node_itself(acl):
    for method in ("PATCH", "PUT"):
        request = acl(_the_acl(), method)[0]
        assert request.path == (
            "/restconf/data/test-native:native/ip/access-list"
            "/test-acl:extended=MS_Access_List_Extended"
        )
        # The body still starts at the node the URL ends on.
        assert list(json.loads(request.body)) == ["test-acl:extended"]


def test_keys_come_first_in_their_entry(acl):
    # Ticked last, but a key identifies the entry and reads best at the top.
    selections = [_sel(f"{ACE}/acl:action", "deny"), _sel(f"{RULE}/acl:sequence", "9"),
                  _sel(f"{EXT}/acl:name", "A")]
    entry = json.loads(acl(selections, "PATCH")[0].body)["test-acl:extended"][0]
    assert list(entry) == ["name", "access-list-seq-rule"]
    assert list(entry["access-list-seq-rule"][0]) == ["sequence", "ace-rule"]


def test_a_choice_never_reaches_the_wire(acl):
    """A choice and its cases are schema only — RFC 7950 section 7.9."""
    request = acl(_the_acl(), "POST")[0]
    assert "choice" not in request.body and "case" not in request.body

    selections = [_sel(f"{EXT}/acl:name", "A"), _sel(f"{RULE}/acl:sequence", "2"),
                  _sel(f"{ACE}/acl:ipv4-address", "10.0.0.0")]
    per_node = acl(selections, "PATCH", compose="per-node")[0]
    assert per_node.path.endswith("/access-list-seq-rule=2/ace-rule/ipv4-address")
    read = acl(selections, "GET")[0]
    assert "choice" not in read.url


# -- choosing the level ------------------------------------------------------


def test_every_level_the_body_could_start_at_is_offered(acl):
    request = acl(_the_acl(), "PATCH")[0]
    assert [t["name"] for t in request.targets] == [
        "native", "ip", "access-list", "extended", "access-list-seq-rule", "ace-rule",
    ]
    # The default holds every selection, keys included: the entry being made.
    assert request.target == EXT


def test_a_higher_target_puts_more_in_the_body(acl):
    request = acl(_the_acl(), "PATCH", target="/ios:native")[0]
    assert request.path == "/restconf/data/test-native:native"
    body = json.loads(request.body)
    # Module names reappear only where ownership changes.
    extended = body["test-native:native"]["ip"]["access-list"]["test-acl:extended"]
    assert extended[0]["name"] == "MS_Access_List_Extended"


def test_a_deeper_target_moves_the_keys_into_the_url(acl):
    request = acl(_the_acl(), "PATCH", target=ACE)[0]
    assert request.path.endswith(
        "/test-acl:extended=MS_Access_List_Extended/access-list-seq-rule=2/ace-rule"
    )
    body = json.loads(request.body)
    assert list(body) == ["test-acl:ace-rule"]
    assert "name" not in json.dumps(body)


def test_a_target_the_selection_has_outgrown_falls_back(acl):
    """Selections change under the target as nodes are ticked; do not fail."""
    request = acl(_the_acl(), "PATCH", target="/ios:native/ios:vlan")[0]
    assert request.target == EXT


def test_post_of_a_top_level_node_goes_to_the_datastore(acl):
    request = acl([_sel("/ios:native/ios:hostname", "r1")], "POST", target="/ios:native")[0]
    assert request.path == "/restconf/data"
    assert json.loads(request.body) == {"test-native:native": {"hostname": "r1"}}


def test_a_lone_leaf_is_written_through_its_parent(acl):
    request = acl([_sel("/ios:native/ios:hostname", "r1")], "PATCH")[0]
    assert request.path == "/restconf/data/test-native:native"
    assert json.loads(request.body) == {"test-native:native": {"hostname": "r1"}}


def test_a_bare_list_entry_can_be_created_from_its_key_alone(acl):
    request = acl([_sel(f"{EXT}/acl:name", "EMPTY")], "POST")[0]
    assert request.path == "/restconf/data/test-native:native/ip/access-list"
    assert json.loads(request.body) == {"test-acl:extended": [{"name": "EMPTY"}]}


# -- what it refuses, and what it warns about ------------------------------------


def test_a_list_without_its_key_is_named(acl):
    selections = [_sel(f"{EXT}/acl:name", "A"), _sel(f"{ACE}/acl:action", "permit")]
    expected = "'access-list-seq-rule' needs a value for its key 'sequence'"
    with pytest.raises(RestconfError, match=expected):
        acl(selections, "PATCH")


def test_nodes_under_different_roots_cannot_share_a_request(acl):
    selections = [_sel("/ios:native/ios:hostname", "r1"), _sel("/ios:motd", "hi")]
    with pytest.raises(RestconfError, match="share no parent"):
        acl(selections, "PATCH")


def test_put_says_what_it_will_remove(acl):
    request = acl(_the_acl(), "PUT")[0]
    assert any("replaces everything under 'extended'" in note for note in request.notes)
    assert acl(_the_acl(), "PATCH")[0].notes == []


def test_per_node_operations_are_called_out(acl):
    selections = _the_acl()
    selections[2]["operation"] = "replace"
    request = acl(selections, "PATCH")[0]
    assert request.method == "PATCH"
    assert any("Per-node operations" in note for note in request.notes)


def test_an_unknown_compose_mode_is_rejected(acl):
    with pytest.raises(RestconfError, match="not a way to compose"):
        acl(_the_acl(), "PATCH", compose="sideways")


def test_reads_and_deletes_are_not_composed(acl):
    """A DELETE of the shared parent would remove far more than was ticked."""
    selections = [_sel(f"{EXT}/acl:name", "A"), _sel(f"{RULE}/acl:sequence", "2"),
                  _sel(f"{ACE}/acl:action"), _sel(f"{ACE}/acl:protocol")]
    deletes = acl(selections, "DELETE")
    assert [r.method for r in deletes] == ["DELETE", "DELETE"]
    assert all(r.path.endswith(("/action", "/protocol")) for r in deletes)
    assert acl(selections, "GET")[0].method == "GET"


# -- values ------------------------------------------------------------------


def test_values_are_typed_the_way_rfc_7951_says(acl):
    selections = [
        _sel(f"{EXT}/acl:name", "A"), _sel(f"{RULE}/acl:sequence", "5"),
        _sel(f"{ACE}/acl:log", "True"), _sel(f"{ACE}/acl:big", "18446744073709551615"),
        _sel(f"{ACE}/acl:dst-eq", "domain"), _sel(f"{ACE}/acl:tag", "1, 2,3", nodetype="leaf-list"),
    ]
    entry = json.loads(acl(selections, "PATCH")[0].body)["test-acl:extended"][0]
    rule = entry["access-list-seq-rule"][0]
    assert rule["sequence"] == 5                       # uint32 is a number
    assert rule["ace-rule"] == {
        "log": True,                                   # boolean, not "True"
        "big": "18446744073709551615",                 # 64-bit stays a string
        "dst-eq": "domain",                            # the union's other member
        "tag": [1, 2, 3],                              # a leaf-list is an array
    }


def test_a_value_that_cannot_be_the_type_is_refused(acl):
    selections = [_sel(f"{EXT}/acl:name", "A"), _sel(f"{RULE}/acl:sequence", "two")]
    with pytest.raises(RestconfError, match="'sequence' is uint32"):
        acl(selections, "PATCH")
    with pytest.raises(RestconfError, match="expected true or false"):
        encode_value(PathNode("log", "m", "leaf", basetype="boolean"), "yes")


def test_an_empty_leaf_needs_no_value_per_node_either(acl):
    """It used to be sent with no body at all, which no device accepts."""
    selections = [_sel(f"{EXT}/acl:name", "A"), _sel(f"{RULE}/acl:sequence", "2"),
                  _sel(f"{ACE}/acl:dst-any")]
    request = acl(selections, "PATCH", compose="per-node")[0]
    assert request.path.endswith("/access-list-seq-rule=2/ace-rule/dst-any")
    assert json.loads(request.body) == {"test-acl:dst-any": [None]}


def test_a_single_leaf_body_is_typed_too():
    load = PathNode("load", "test-base", "leaf", basetype="uint8")
    assert json.loads(build_body(load, "50")) == {"test-base:load": 50}


# -- a request written by hand ---------------------------------------------------


def test_a_pasted_url_is_reduced_to_its_path():
    request = raw_request("post", "https://{{ router }}/restconf/data/native/ip/access-list", "{}")
    assert (request.method, request.path) == ("POST", "/restconf/data/native/ip/access-list")
    assert request.content_type == "application/yang-data+json"


def test_a_query_string_survives():
    request = raw_request("GET", "/restconf/data/native?depth=2&content=config")
    assert request.url == "/restconf/data/native?depth=2&content=config"


def test_reads_and_deletes_send_no_body():
    assert raw_request("DELETE", "/restconf/data/x", '{"a": 1}').body == ""


@pytest.mark.parametrize(
    ("method", "url", "body", "message"),
    [
        ("FETCH", "/restconf/data", "", "not a RESTCONF method"),
        ("GET", "restconf/data", "", "must be a path on the device"),
        ("GET", "//evil.example/restconf", "", "must be a path on the device"),
        ("GET", "/restconf/data/a b", "", "whitespace"),
        ("POST", "/restconf/data", '{"a": }', "not valid JSON"),
    ],
)
def test_what_a_hand_written_request_is_refused_for(method, url, body, message):
    with pytest.raises(RestconfError, match=message):
        raw_request(method, url, body)


def test_send_endpoint_reports_a_bad_body_before_touching_the_device(client):
    client.post("/api/devices", json={"name": "r1", "address": "192.0.2.1"})
    reply = client.post(
        "/api/restconf/send",
        json={"device": "r1", "method": "POST", "url": "/restconf/data", "body": "{nope"},
    )
    assert reply.status_code == 400
    assert "not valid JSON" in reply.json()["detail"]
