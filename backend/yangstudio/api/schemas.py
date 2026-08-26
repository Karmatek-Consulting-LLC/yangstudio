"""Pydantic request/response models for the HTTP API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RepoCreate(BaseModel):
    name: str
    description: str = ""


class RepoGitImport(BaseModel):
    url: str
    ref: str = ""
    subdirectory: str = ""


class ModuleRef(BaseModel):
    name: str
    revision: str = ""
    # Advertised by a device; narrows the parsed tree to what it implements.
    features: list[str] = Field(default_factory=list)
    deviations: list[str] = Field(default_factory=list)


class YangSetCreate(BaseModel):
    name: str
    repository: str
    modules: list[ModuleRef] = Field(default_factory=list)


class YangSetUpdate(BaseModel):
    name: str | None = None
    modules: list[ModuleRef] | None = None


class YangSetFromDevice(BaseModel):
    """Build a set from what a device advertises, matched against a repository."""

    name: str
    repository: str
    device: str
    # Restrict to these module names; empty means everything advertised that
    # the repository actually holds.
    modules: list[str] = Field(default_factory=list)
    include_features: bool = True


class YangSetFromModules(BaseModel):
    """Build a set from an explicit module-name list (e.g. a finished download)."""

    name: str
    repository: str
    modules: list[str]


class DeviceCreate(BaseModel):
    name: str
    address: str = ""
    username: str = ""
    password: str = ""
    description: str = ""
    variant: str = "generic"
    protocols: dict = Field(default_factory=dict)


class DeviceUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    username: str | None = None
    password: str | None = None
    description: str | None = None
    variant: str | None = None
    protocols: dict | None = None


class SelectionIn(BaseModel):
    xpath: str
    value: str = ""
    operation: str = ""
    nodetype: str = "leaf"
    datatype: str = ""
    is_key: bool = False


class RpcBuild(BaseModel):
    operation: str = "get-config"
    datastore: str = "running"
    selections: list[SelectionIn] = Field(default_factory=list)
    namespaces: dict[str, str] = Field(default_factory=dict)
    with_defaults: str = ""


class RpcRun(RpcBuild):
    device: str
    rpc_xml: str = ""     # If set, run this verbatim instead of rebuilding.


class RestconfBuild(BaseModel):
    """Selections resolved into RESTCONF calls against a set's tree."""

    yangset: str
    operation: str = "GET"          # GET | PUT | PATCH | POST | DELETE
    selections: list[SelectionIn] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)


class RestconfRun(RestconfBuild):
    device: str
    # Run only this one of the planned requests; omit to run them all in order.
    only: int | None = None


class SchemaDownload(BaseModel):
    modules: list[str]
    repository: str = ""      # If set, save the downloaded schemas here.
