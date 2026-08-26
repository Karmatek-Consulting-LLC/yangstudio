"""Device profiles: how to reach a box, per protocol.

Upstream models this as a base profile plus per-protocol plugins that
*inherit* address/credentials from the base unless overridden. That
inheritance is genuinely useful — most devices use one address and one
credential for every protocol — so it is kept here, just expressed plainly.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import get_settings
from .storage import StorageError, slugify

PROTOCOLS = ("netconf", "restconf", "gnmi", "ssh")

DEFAULT_PORTS = {"netconf": 830, "restconf": 443, "gnmi": 50051, "ssh": 22}


@dataclass
class ProtocolConfig:
    """Per-protocol overrides. Empty fields fall back to the profile base."""

    enabled: bool = False
    address: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    # NETCONF-specific niceties.
    device_variant: str = ""     # iosxe | iosxr | nxos | generic


@dataclass
class Device:
    """A named device profile."""

    slug: str
    name: str
    address: str = ""
    username: str = ""
    password: str = ""
    description: str = ""
    variant: str = "generic"
    protocols: dict = field(default_factory=dict)
    created: str = ""
    modified: str = ""

    @property
    def path(self) -> Path:
        return get_settings().devices_dir / f"{self.slug}.json"

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def create(cls, name: str, **kwargs) -> Device:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        device = cls(slug=slugify(name), name=name, created=now, modified=now)
        device.apply(kwargs)
        if device.path.exists():
            raise StorageError(f"device {device.slug!r} already exists")
        device.save()
        return device

    @classmethod
    def load(cls, slug: str) -> Device:
        path = get_settings().devices_dir / f"{slugify(slug)}.json"
        if not path.is_file():
            raise StorageError(f"no such device: {slug!r}")
        data = json.loads(path.read_text())
        data.pop("slug", None)
        return cls(slug=path.stem, **data)

    @classmethod
    def all(cls) -> list[Device]:
        root = get_settings().devices_dir
        out = []
        for p in sorted(root.glob("*.json")):
            try:
                out.append(cls.load(p.stem))
            except (StorageError, ValueError, TypeError):
                continue
        return sorted(out, key=lambda d: d.name.lower())

    def apply(self, data: dict) -> None:
        """Update mutable fields from a dict, ignoring unknown keys."""
        for key in ("name", "address", "username", "password", "description", "variant"):
            if key in data and data[key] is not None:
                setattr(self, key, data[key])
        protocols = data.get("protocols")
        if isinstance(protocols, dict):
            for proto, cfg in protocols.items():
                if proto in PROTOCOLS and isinstance(cfg, dict):
                    self.protocols[proto] = cfg

    def save(self) -> None:
        self.modified = datetime.now(UTC).isoformat(timespec="seconds")
        self.path.write_text(json.dumps(asdict(self), indent=2))

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)

    # -- resolution --------------------------------------------------------

    def resolve(self, protocol: str) -> ProtocolConfig:
        """Effective connection settings for ``protocol``, after inheritance."""
        if protocol not in PROTOCOLS:
            raise StorageError(f"unknown protocol: {protocol!r}")
        raw = self.protocols.get(protocol, {}) or {}
        return ProtocolConfig(
            enabled=bool(raw.get("enabled", False)),
            address=raw.get("address") or self.address,
            port=int(raw.get("port") or DEFAULT_PORTS[protocol]),
            username=raw.get("username") or self.username,
            password=raw.get("password") or self.password,
            device_variant=raw.get("device_variant") or self.variant,
        )

    def redacted(self) -> dict:
        """Serialisable form with every password removed."""
        data = asdict(self)
        data["password"] = "********" if self.password else ""
        data["has_password"] = bool(self.password)
        protocols = {}
        for proto, cfg in (data.get("protocols") or {}).items():
            cfg = dict(cfg)
            if cfg.get("password"):
                cfg["password"] = "********"
            protocols[proto] = cfg
        data["protocols"] = protocols
        return data
