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


# -- choosing between two libraries -----------------------------------------

# A device can serve both versions and put download locations in only one.
# Seen on IOS-XE behind a sandbox gateway: the RFC 8525 library lists every
# module with nothing but a name, namespace and revision.
BARE_8525 = {
    "ietf-yang-library:yang-library": {
        "module-set": [
            {
                "name": "common",
                "module": [
                    {"name": "ietf-interfaces", "revision": "2014-05-08",
                     "namespace": "urn:ietf:params:xml:ns:yang:ietf-interfaces"},
                    {"name": "ietf-yang-types", "revision": "2013-07-15"},
                ],
            }
        ]
    }
}

USEFUL_7895 = {
    "ietf-yang-library:modules-state": {
        "module": [
            {"name": "ietf-interfaces", "revision": "2014-05-08",
             "schema": "https://10.4.19.105:443/restconf/tailf/modules/ietf-interfaces/2014-05-08"},
            {"name": "ietf-yang-types", "revision": "2013-07-15",
             "schema": "https://10.4.19.105:443/restconf/tailf/modules/ietf-yang-types/2013-07-15"},
        ]
    }
}


def _both_libraries(request):
    """A device that answers both, only one of them usefully."""
    if request.url.path.endswith("host-meta"):
        return httpx.Response(404)
    if "ietf-yang-library:yang-library" in str(request.url):
        return httpx.Response(200, json=BARE_8525)
    if "modules-state" in str(request.url):
        return httpx.Response(200, json=USEFUL_7895)
    return None


def test_prefers_the_library_it_can_download_from(device, monkeypatch):
    """Listing modules is no use if there is no way to fetch any of them."""
    def handler(request):
        preset = _both_libraries(request)
        return preset if preset is not None else httpx.Response(404)

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    caps = restconf.capabilities(device)

    # The newer library answered first, but the older one is the usable one.
    assert caps["yang_library"] == "modules-state"
    assert caps["module_count"] == 2
    assert caps["downloadable"] == 2


def test_a_library_without_locations_is_still_better_than_nothing(device, monkeypatch):
    """If it is all the device has, the module list is worth reporting."""
    def handler(request):
        if request.url.path.endswith("host-meta"):
            return httpx.Response(404)
        if "ietf-yang-library:yang-library" in str(request.url):
            return httpx.Response(200, json=BARE_8525)
        return httpx.Response(404)

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    caps = restconf.capabilities(device)

    assert caps["module_count"] == 2
    assert caps["downloadable"] == 0


def test_downloading_with_no_locations_anywhere_says_so_once(device, monkeypatch):
    """One clear refusal, rather than a failure per module."""
    def handler(request):
        if request.url.path.endswith("host-meta"):
            return httpx.Response(404)
        if "ietf-yang-library:yang-library" in str(request.url):
            return httpx.Response(200, json=BARE_8525)
        return httpx.Response(404)

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    with pytest.raises(restconf.RestconfError, match="no download URL for any"):
        restconf.download_schemas(device, ["ietf-interfaces"])


# -- URLs that are advertised but not served --------------------------------

def test_a_wall_of_404s_stops_quickly_and_explains_itself(device, monkeypatch):
    """A gateway proxying only /restconf/data 404s every schema URL.

    The module list is correct and every entry carries a URL, so nothing looks
    wrong until the fetches start. Marching through six hundred of them to
    collect six hundred 404s helps nobody.
    """
    names = [f"m{i}" for i in range(200)]
    library = {
        "ietf-yang-library:modules-state": {
            "module": [
                {"name": n, "schema": f"https://10.4.19.105:443/restconf/tailf/modules/{n}"}
                for n in names
            ]
        }
    }

    def handler(request):
        if request.url.path.endswith("host-meta"):
            return httpx.Response(404)
        if "ietf-yang-library:yang-library" in str(request.url):
            return httpx.Response(404)
        if "modules-state" in str(request.url):
            return httpx.Response(200, json=library)
        return httpx.Response(404)          # every schema URL

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    result = restconf.download_schemas(device, names)

    assert len(result["errors"]) == restconf.MAX_CONSECUTIVE_FAILURES
    assert "only proxies /restconf/data" in result["aborted"]
    assert "NETCONF" in result["aborted"]


def test_a_module_listed_without_a_url_is_told_apart_from_an_unknown_one(
    device, monkeypatch,
):
    library = {
        "ietf-yang-library:modules-state": {
            "module": [
                {"name": "listed-only"},
                {"name": "fetchable", "schema": "/yang/fetchable"},
            ]
        }
    }

    def handler(request):
        if request.url.path.endswith("host-meta"):
            return httpx.Response(404)
        if "ietf-yang-library:yang-library" in str(request.url):
            return httpx.Response(404)
        if "modules-state" in str(request.url):
            return httpx.Response(200, json=library)
        return httpx.Response(200, text="module fetchable { }")

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    result = restconf.download_schemas(device, ["listed-only", "never-heard-of"])

    assert "publishes no download URL" in result["errors"]["listed-only"]
    assert "not in the device's YANG library" in result["errors"]["never-heard-of"]


# -- saying what was actually tried -----------------------------------------

def test_a_wrong_address_names_the_urls_it_tried(device, monkeypatch):
    """404 everywhere is usually the address, not a device without a library.

    Sandbox gateways route by hostname and answer 404 to every path under a
    name they do not recognise. That is indistinguishable from a device with
    no YANG library unless the error says which URL it asked for.
    """
    def handler(request):
        return httpx.Response(404)

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    with pytest.raises(restconf.RestconfError) as caught:
        restconf.capabilities(device)

    message = str(caught.value)
    assert "ietf-yang-library:yang-library -> HTTP 404" in message
    assert "ietf-yang-library:modules-state -> HTTP 404" in message
    # httpx drops the default port when it renders the URL; what matters is
    # that the host the request actually went to is in the message.
    assert "https://10.0.0.1/restconf" in message
    # And it should point at the likely cause rather than the unlikely one.
    assert "address on the device profile" in message


def test_a_device_answering_without_a_library_is_described_differently(
    device, monkeypatch,
):
    """200 with the wrong body is a real missing-library, not a bad address."""
    def handler(request):
        if request.url.path.endswith("host-meta"):
            return httpx.Response(404)
        return httpx.Response(200, json={"something-else": {}})

    monkeypatch.setattr(restconf, "_client", _serve(handler))
    with pytest.raises(restconf.RestconfError) as caught:
        restconf.capabilities(device)

    message = str(caught.value)
    assert "no modules in it" in message
    assert "must implement" not in message
    assert "address on the device profile" not in message
    assert "RFC 8525 or RFC 7895" in message


# -- one module is the same problem as six hundred --------------------------

def _one_module_404s(request):
    library = {
        "ietf-yang-library:modules-state": {
            "module": [
                {"name": "ietf-interfaces", "revision": "2014-05-08",
                 "schema": "https://10.4.19.105:443/restconf/tailf/modules/ietf-interfaces/2014-05-08"},
            ]
        }
    }
    if request.url.path.endswith("host-meta"):
        return httpx.Response(404)
    if "ietf-yang-library:yang-library" in str(request.url):
        return httpx.Response(404)
    if "modules-state" in str(request.url):
        return httpx.Response(200, json=library)
    return httpx.Response(404)          # the schema URL


def test_a_single_404_still_explains_itself(device, monkeypatch):
    """The guidance must not depend on having asked for enough modules.

    A run of failures long enough to abort gets an explanation. Asking for one
    module and getting one 404 is the same problem, and used to come back as
    a bare status code.
    """
    monkeypatch.setattr(restconf, "_client", _serve(_one_module_404s))
    result = restconf.download_schemas(device, ["ietf-interfaces"])

    assert result["schemas"] == {}
    assert "only proxies /restconf/data" in result["aborted"]
    assert "NETCONF" in result["aborted"]


def test_a_404_names_the_url_the_device_advertised(device, monkeypatch):
    """Seeing the URL is most of the diagnosis."""
    monkeypatch.setattr(restconf, "_client", _serve(_one_module_404s))
    result = restconf.download_schemas(device, ["ietf-interfaces"])

    message = result["errors"]["ietf-interfaces"]
    assert "/restconf/tailf/modules/ietf-interfaces/2014-05-08" in message
    # Re-homed onto the address that was actually reached, not the inside one.
    assert "10.4.19.105" not in message
    assert "10.0.0.1" in message


def test_a_partial_download_is_not_labelled_a_gateway_problem(device, monkeypatch):
    """One module missing among several that worked is a different story."""
    library = {
        "ietf-yang-library:modules-state": {
            "module": [
                {"name": "gone", "schema": "/yang/gone"},
                {"name": "here", "schema": "/yang/here"},
            ]
        }
    }

    def handler(request):
        if request.url.path.endswith("host-meta"):
            return httpx.Response(404)
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
    assert result["aborted"] == ""
