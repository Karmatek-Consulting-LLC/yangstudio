"""Shared fixtures: an isolated data root and a repo of real YANG modules."""
from __future__ import annotations

import textwrap

import pytest


@pytest.fixture(autouse=True)
def data_root(tmp_path, monkeypatch):
    """Point every test at a throwaway data directory."""
    monkeypatch.setenv("YANGSTUDIO_DATA", str(tmp_path / "data"))
    from yangstudio.core import config

    config.get_settings.cache_clear()
    yield tmp_path / "data"
    config.get_settings.cache_clear()


BASE_MODULE = textwrap.dedent(
    """
    module test-base {
      yang-version 1.1;
      namespace "urn:example:test-base";
      prefix tb;

      revision 2024-01-01 { description "Initial."; }
      revision 2023-01-01 { description "Older."; }

      identity protocol { description "Base protocol."; }
      identity tcp { base protocol; }
      identity secure-tcp { base tcp; }

      typedef percent {
        type uint8 { range "0..100"; }
        units "percent";
      }

      container config {
        description "Writable configuration.";
        leaf hostname {
          type string { length "1..64"; pattern "[a-zA-Z0-9-]+"; }
          mandatory true;
          description "Device hostname.";
        }
        leaf load {
          type percent;
          description "Load percentage.";
        }
        leaf proto {
          type identityref { base protocol; }
        }
        leaf mode {
          type enumeration {
            enum fast { value 1; }
            enum slow { value 2; }
          }
        }
        list peer {
          key "id";
          leaf id { type string; }
          leaf address { type string; }
        }
      }

      container state {
        config false;
        description "Read-only operational state.";
        leaf uptime { type uint32; units "seconds"; }
      }

      rpc reboot {
        description "Reboot the device.";
        input { leaf delay { type uint16; } }
        output { leaf result { type string; } }
      }
    }
    """
).strip()


@pytest.fixture
def repo_with_modules():
    """A repository containing the test module, plus its parsed set."""
    from yangstudio.core.storage import Repository, YangSet

    repo = Repository.create("test-repo")
    (repo.path / "test-base@2024-01-01.yang").write_text(BASE_MODULE)
    repo.modules(refresh=True)
    yangset = YangSet.create(
        "test-set", repo.slug, [{"name": "test-base", "revision": "2024-01-01"}]
    )
    return repo, yangset


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from yangstudio.app import app

    return TestClient(app)
