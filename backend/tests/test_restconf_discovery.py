"""Reading a device's YANG library over RESTCONF, and downloading from it.

Devices disagree about which version of ietf-yang-library they publish and
about where they claim to live, so most of what is pinned here is tolerance of
those differences rather than the happy path.
"""
import httpx
import pytest

from yangstudio.core.devices import Device
from yangstudio.services import restconf


@pytest.fixture
def device():
    return Device.create("r1", address="10.0.0.1", username="u", password="p")


# RFC 7895: `schema` is one leaf, deviations are objects.
MODULES_STATE = {
    "ietf-yang-library:modules-state": {
        "module-set-id": "abc123",
        "module": [
            {
                "name": "ietf-interfaces",
                "revision": "2018-02-20",
                "namespace": "urn:ietf:params:xml:ns:yang:ietf-interfaces",
                "schema": "https://10.0.0.1:443/restconf/tailf/modules/ietf-interfaces/2018-02-20",
                "conformance-type": "implement",
                "feature": ["if-mib"],
                "deviation": [{"name": "vendor-if-deviation", "revision": "2019-01-01"}],
            },
            {
                "name": "ietf-yang-types",
                "revision": "2013-07-15",
                "schema": "https://10.0.0.1:443/restconf/tailf/modules/ietf-yang-types/2013-07-15",
                "conformance-type": "import",
            },
        ],
    }
}

# RFC 8525: `location` is a leaf-list, deviations are bare names.
YANG_LIBRARY = {
    "ietf-yang-library:yang-library": {
        "module-set": [
            {
                "name": "default",
                "module": [
                    {
                        "name": "ietf-interfaces",
                        "revision": "2018-02-20",
                        "location": ["https://10.0.0.1/yang/ietf-interfaces.yang"],
                        "feature": ["if-mib"],
                        "deviation": ["vendor-if-deviation"],
                        "submodule": [
                            {
                                "name": "ietf-interfaces-body",
                                "revision": "2018-02-20",
                                "location": ["https://10.0.0.1/yang/body.yang"],
                            }
                        ],
                    }
                ],
                "import-only-module": [
                    {
                        "name": "ietf-yang-types",
                        "revision": "2013-07-15",
                        "location": ["https://10.0.0.1/yang/ietf-yang-types.yang"],
                    }
                ],
            }
        ]
    }
}


# -- reading the library ----------------------------------------------------

def test_reads_the_2016_library():
    modules, submodules = restconf._extract_library(MODULES_STATE)
    assert [m["name"] for m in modules] == ["ietf-interfaces", "ietf-yang-types"]
    assert modules[0]["features"] == ["if-mib"]
    assert modules[0]["deviations"] == ["vendor-if-deviation"]
    assert modules[0]["conformance"] == "implement"
    assert submodules == {}


def test_reads_the_rfc_8525_library():
    modules, submodules = restconf._extract_library(YANG_LIBRARY)
    assert [m["name"] for m in modules] == ["ietf-interfaces", "ietf-yang-types"]
    # A leaf-list of names, not a list of objects, but the same answer.
    assert modules[0]["deviations"] == ["vendor-if-deviation"]
    # import-only modules are still modules, marked as such.
    assert modules[1]["conformance"] == "import"
    assert submodules == {"ietf-interfaces-body": "https://10.0.0.1/yang/body.yang"}


def test_location_stands_in_for_schema():
    assert restconf._schema_url({"schema": "/a"}) == "/a"
    assert restconf._schema_url({"location": ["/b", "/c"]}) == "/b"
    assert restconf._schema_url({}) == ""


def test_the_same_module_in_two_sets_is_listed_once():
    doubled = {
        "ietf-yang-library:yang-library": {
            "module-set": [
                {"module": [{"name": "m", "revision": "1"}]},
                {"module": [{"name": "m", "revision": "1"}]},
            ]
        }
    }
    modules, _ = restconf._extract_library(doubled)
    assert len(modules) == 1


def test_a_library_with_no_modules_is_not_a_library():
    modules, _ = restconf._extract_library({"something-else": {}})
    assert modules == []


# -- the address the device claims ------------------------------------------

def test_schema_urls_are_rehomed_onto_the_address_that_worked(device):
    """A device behind NAT advertises an address that does not work from here.

    The sandbox case: the router believes it is 10.10.20.48, but it is only
    reachable on the address the profile was configured with. Keep the path,
    drop the rest.
    """
    claimed = "https://10.10.20.48:443/restconf/tailf/modules/foo/2020-01-01"
    assert restconf._rehome(device, claimed) == (
        "https://10.0.0.1:443/restconf/tailf/modules/foo/2020-01-01"
    )


def test_a_relative_schema_url_is_made_absolute(device):
    assert restconf._rehome(device, "/restconf/tailf/modules/foo") == (
        "https://10.0.0.1:443/restconf/tailf/modules/foo"
    )
    assert restconf._rehome(device, "restconf/tailf/modules/foo") == (
        "https://10.0.0.1:443/restconf/tailf/modules/foo"
    )


# -- downloading ------------------------------------------------------------

def _serve(handler):
    """Point the service's HTTP client at a scripted transport."""
    def factory(timeout):
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="")
    return factory


def _library_reply(request):
    if "ietf-yang-library:yang-library" in str(request.url):
        return httpx.Response(404)
    if "modules-state" in str(request.url):
        return httpx.Response(200, json=MODULES_STATE)
    return None


def test_download_follows_imports(device, monkeypatch):
    def handler(request):
        preset = _library_reply(request)
        if preset is not None:
            return preset
        if request.url.path.endswith("host-meta"):
            return httpx.Response(404)
        if "ietf-interfaces" in request.url.path:
            return httpx.Response(
                200,
                text='module ietf-interfaces { import ietf-yang-types { prefix yang; } }',
            )
        if "ietf-yang-types" in request.url.path:
            return httpx.Response(200, text="module ietf-yang-types { }")
        return httpx.Response(404)

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    result = restconf.download_schemas(device, ["ietf-interfaces"])

    assert sorted(result["schemas"]) == ["ietf-interfaces", "ietf-yang-types"]
    # The import was not asked for, so it is reported as pulled in.
    assert result["pulled_in"] == ["ietf-yang-types"]
    assert result["errors"] == {}


def test_a_module_missing_from_the_library_is_reported_not_guessed(device, monkeypatch):
    def handler(request):
        preset = _library_reply(request)
        if preset is not None:
            return preset
        return httpx.Response(404)

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    result = restconf.download_schemas(device, ["not-advertised"])

    assert result["schemas"] == {}
    assert "not in the device's YANG library" in result["errors"]["not-advertised"]


def test_a_200_that_is_not_yang_source_is_an_error(device, monkeypatch):
    """Some devices answer an error document with 200 and a JSON body."""
    def handler(request):
        preset = _library_reply(request)
        if preset is not None:
            return preset
        return httpx.Response(200, json={"errors": "nope"})

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    result = restconf.download_schemas(device, ["ietf-interfaces"])

    assert result["schemas"] == {}
    assert "did not return YANG source" in result["errors"]["ietf-interfaces"]


def test_a_run_of_server_errors_stops_the_download(device, monkeypatch):
    """A device that has stopped answering should be said so, not waited on."""
    names = [f"m{i}" for i in range(40)]
    library = {
        "ietf-yang-library:modules-state": {
            "module": [{"name": n, "schema": f"/yang/{n}"} for n in names]
        }
    }

    def handler(request):
        if "ietf-yang-library:yang-library" in str(request.url):
            return httpx.Response(404)
        if "modules-state" in str(request.url):
            return httpx.Response(200, json=library)
        return httpx.Response(503)

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    result = restconf.download_schemas(device, names)

    assert result["aborted"]
    assert len(result["errors"]) == restconf.MAX_CONSECUTIVE_FAILURES


def test_a_404_on_one_module_does_not_stop_the_rest(device, monkeypatch):
    """Unlike a dead NETCONF session, one refusal says nothing about the next."""
    library = {
        "ietf-yang-library:modules-state": {
            "module": [
                {"name": "gone", "schema": "/yang/gone"},
                {"name": "here", "schema": "/yang/here"},
            ]
        }
    }

    def handler(request):
        if "ietf-yang-library:yang-library" in str(request.url):
            return httpx.Response(404)
        if "modules-state" in str(request.url):
            return httpx.Response(200, json=library)
        if request.url.path.endswith("/gone"):
            return httpx.Response(404)
        return httpx.Response(200, text="module here { }")

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    result = restconf.download_schemas(device, ["gone", "here"])

    assert sorted(result["schemas"]) == ["here"]
    assert "gone" in result["errors"]
    assert result["aborted"] == ""


def test_cancelling_stops_between_modules(device, monkeypatch):
    library = {
        "ietf-yang-library:modules-state": {
            "module": [{"name": f"m{i}", "schema": f"/yang/m{i}"} for i in range(10)]
        }
    }

    def handler(request):
        if "ietf-yang-library:yang-library" in str(request.url):
            return httpx.Response(404)
        if "modules-state" in str(request.url):
            return httpx.Response(200, json=library)
        return httpx.Response(200, text="module x { }")

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 3

    result = restconf.download_schemas(
        device, [f"m{i}" for i in range(10)], should_cancel=cancel
    )
    assert 0 < len(result["schemas"]) < 10


# -- capabilities -----------------------------------------------------------

def test_capabilities_match_the_shape_netconf_returns(device, monkeypatch):
    """Everything downstream reads one shape, whichever transport found it."""
    def handler(request):
        if request.url.path.endswith("host-meta"):
            return httpx.Response(404)
        preset = _library_reply(request)
        if preset is not None:
            return preset
        if "restconf-monitoring" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "ietf-restconf-monitoring:capabilities": {
                        "capability": ["urn:ietf:params:restconf:capability:depth:1.0"]
                    }
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    caps = restconf.capabilities(device)

    required = {
        "session_id", "base_capabilities", "modules", "module_count",
        "supports_candidate", "supports_startup", "supports_validate",
        "supports_netconf_monitoring",
    }
    assert required <= set(caps)
    assert caps["transport"] == "restconf"
    assert caps["module_count"] == 2
    assert caps["downloadable"] == 2
    assert caps["yang_library"] == "modules-state"
    assert caps["base_capabilities"] == [
        "urn:ietf:params:restconf:capability:depth:1.0"
    ]


def test_a_device_without_a_yang_library_says_so(device, monkeypatch):
    def handler(request):
        return httpx.Response(404)

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    with pytest.raises(restconf.RestconfError, match="ietf-yang-library"):
        restconf.capabilities(device)


def test_bad_credentials_are_named_as_such(device, monkeypatch):
    def handler(request):
        if request.url.path.endswith("host-meta"):
            return httpx.Response(404)
        return httpx.Response(401)

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    with pytest.raises(restconf.RestconfError, match="rejected the credentials"):
        restconf.capabilities(device)
