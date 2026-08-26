"""Connection failures must say what to do about them.

These are the messages a user sees when a device will not talk, so they are
worth pinning: "Unexpected session close" is technically accurate and
practically useless.
"""
from unittest.mock import patch

import pytest
from ncclient.transport.errors import AuthenticationError, SessionCloseError, SSHError

from yangstudio.core.devices import Device
from yangstudio.services import netconf


@pytest.fixture
def device():
    return Device.create(
        "r1", address="10.0.0.1", username="admin", password="admin", variant="iosxe"
    )


def _connect_raising(exc):
    return patch("yangstudio.services.netconf.manager.connect", side_effect=exc)


def test_session_close_explains_aaa(device):
    """The device hung up after the subsystem opened: an authorization problem."""
    with _connect_raising(SessionCloseError(b"")):
        with pytest.raises(netconf.NetconfError) as caught:
            netconf.get_session(device, reuse=False)
    message = str(caught.value)
    # It must name the real cause rather than repeat ncclient's wording.
    assert "authorization problem, not a credential one" in message
    assert "aaa authorization exec default local" in message
    assert "dmiauthd" in message
    assert "Unexpected session close" not in message


def test_auth_failure_points_at_credentials(device):
    with _connect_raising(AuthenticationError("nope")):
        with pytest.raises(netconf.NetconfError, match="Check the username and password"):
            netconf.get_session(device, reuse=False)


def test_unreachable_names_host_and_port(device):
    with _connect_raising(SSHError("timed out")):
        with pytest.raises(netconf.NetconfError, match=r"cannot reach 10\.0\.0\.1:830"):
            netconf.get_session(device, reuse=False)


def test_missing_address_is_caught_before_dialling(device):
    device.address = ""
    with pytest.raises(netconf.NetconfError, match="has no address"):
        netconf.get_session(device, reuse=False)


def test_timed_out_rpc_drops_the_session(device):
    """A desynchronised session must not be reused, or every later RPC fails."""
    from ncclient.operations.errors import TimeoutExpiredError

    fake = type("Conn", (), {"dispatch": lambda self, op: (_ for _ in ()).throw(
        TimeoutExpiredError("ncclient timed out"))})()
    with patch("yangstudio.services.netconf.get_session", return_value=fake):
        with patch("yangstudio.services.netconf.close_session") as closer:
            result = netconf.run_rpc(device, "<rpc><get/></rpc>")

    assert result["ok"] is False
    assert result["session_reset"] is True
    closer.assert_called_once_with(device.slug)
    assert "did not reply within" in result["error"]["message"]
    assert "try again and it will reconnect" in result["error"]["message"]


def test_rpc_error_keeps_the_session(device):
    """The device answering 'no' says nothing about the transport."""
    from ncclient.operations import RPCError

    # RPCError exposes tag/severity as read-only properties, so build it the
    # way ncclient does rather than assigning to them.
    error = RPCError.__new__(RPCError)
    Exception.__init__(error, "unknown-element")

    fake = type("Conn", (), {"dispatch": lambda self, op: (_ for _ in ()).throw(error)})()
    with patch("yangstudio.services.netconf.get_session", return_value=fake):
        with patch("yangstudio.services.netconf.close_session") as closer:
            result = netconf.run_rpc(device, "<rpc><get/></rpc>")

    assert result["ok"] is False
    assert "session_reset" not in result
    closer.assert_not_called()


def test_transport_failure_during_capabilities_drops_the_session(device):
    from ncclient.transport.errors import SessionCloseError

    class Conn:
        @property
        def server_capabilities(self):
            raise SessionCloseError(b"")

    with patch("yangstudio.services.netconf.get_session", return_value=Conn()):
        with patch("yangstudio.services.netconf.close_session") as closer:
            with pytest.raises(netconf.NetconfError, match="has been closed"):
                netconf.capabilities(device)
    closer.assert_called_once_with(device.slug)


def test_prettify_reindents_a_one_line_reply():
    """Devices send replies on one line; that is correct on the wire, unreadable on screen."""
    compact = (
        '<rpc-reply xmlns="urn:x"><data><interfaces><interface>'
        "<name>Gi1</name><description>uplink</description>"
        "</interface></interfaces></data></rpc-reply>"
    )
    pretty = netconf.prettify(compact)
    assert pretty.count("\n") >= 6
    assert "  <data>" in pretty
    assert "uplink" in pretty


def test_prettify_leaves_non_xml_alone():
    assert netconf.prettify("not xml at all") == "not xml at all"
    assert netconf.prettify("") == ""


def test_prettify_skips_very_large_payloads():
    """Re-indenting a huge reply helps nobody and costs seconds."""
    big = "<a>" + ("x" * (netconf.MAX_PRETTY_BYTES + 10)) + "</a>"
    assert netconf.prettify(big) is big
