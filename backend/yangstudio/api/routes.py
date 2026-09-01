"""HTTP API. Thin translation between JSON and the core modules."""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..core import rpc as rpc_core
from ..core.devices import PROTOCOLS, Device
from ..core.quickparse import parse_file
from ..core.storage import Repository, StorageError, YangSet
from ..core.tree import TreeError
from ..services import explorer
from ..services import netconf as netconf_svc
from ..services import restconf as restconf_svc
from ..services.jobs import registry
from . import schemas as S

router = APIRouter(prefix="/api")


def _module_dict(info) -> dict:
    """Serialise a ModuleInfo, including its computed ``key``.

    ``asdict`` drops properties, and the client keys module selection off
    ``key``, so it has to be added explicitly.
    """
    data = asdict(info)
    data["key"] = info.key
    return data


def _wrap(exc: Exception) -> HTTPException:
    """Map internal errors onto sensible HTTP statuses."""
    if isinstance(exc, StorageError):
        message = str(exc)
        status = 404 if "no such" in message else 400
        return HTTPException(status_code=status, detail=message)
    if isinstance(exc, (TreeError, rpc_core.RpcError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, netconf_svc.NetconfError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, restconf_svc.RestconfError):
        message = str(exc)
        # "cannot reach" is the device's fault; the rest is a bad selection.
        status = 502 if "cannot reach" in message else 400
        return HTTPException(status_code=status, detail=message)
    return HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------
# Repositories
# --------------------------------------------------------------------------

@router.get("/repositories")
def list_repositories() -> list[dict]:
    out = []
    for repo in Repository.all():
        modules = repo.modules()
        out.append(
            {
                "slug": repo.slug,
                "name": repo.name,
                "description": repo.description,
                "created": repo.created,
                "module_count": len(modules),
            }
        )
    return out


@router.post("/repositories", status_code=201)
def create_repository(body: S.RepoCreate) -> dict:
    try:
        repo = Repository.create(body.name, body.description)
    except StorageError as exc:
        raise _wrap(exc) from exc
    return {"slug": repo.slug, "name": repo.name, "module_count": 0}


@router.get("/repositories/{slug}")
def get_repository(slug: str, refresh: bool = False) -> dict:
    try:
        repo = Repository.load(slug)
        modules = repo.modules(refresh=refresh)
    except StorageError as exc:
        raise _wrap(exc) from exc
    return {
        "slug": repo.slug,
        "name": repo.name,
        "description": repo.description,
        "modules": [_module_dict(m) for m in modules],
        "module_count": len(modules),
    }


@router.delete("/repositories/{slug}", status_code=204)
def delete_repository(slug: str) -> None:
    try:
        Repository.load(slug).delete()
    except StorageError as exc:
        raise _wrap(exc) from exc


@router.post("/repositories/{slug}/upload")
async def upload_to_repository(slug: str, files: list[UploadFile] = File(...)) -> dict:
    try:
        repo = Repository.load(slug)
    except StorageError as exc:
        raise _wrap(exc) from exc

    added, skipped = [], []
    for upload in files:
        content = await upload.read()
        try:
            info = repo.add_file(upload.filename or "", content)
        except StorageError as exc:
            skipped.append({"file": upload.filename, "reason": str(exc)})
            continue
        if info is None:
            skipped.append({"file": upload.filename, "reason": "not a YANG module"})
        else:
            added.append({"name": info.name, "revision": info.revision})
    repo.modules(refresh=True)
    return {"added": added, "skipped": skipped}


@router.post("/repositories/{slug}/import-git")
def import_git(slug: str, body: S.RepoGitImport) -> dict:
    """Clone a git repo and copy its ``.yang`` files into this repository."""
    try:
        repo = Repository.load(slug)
    except StorageError as exc:
        raise _wrap(exc) from exc

    from git import GitCommandError
    from git import Repo as GitRepo

    with tempfile.TemporaryDirectory() as tmp:
        try:
            # Shallow clone: these repos are large and history is irrelevant.
            cloned = GitRepo.clone_from(body.url, tmp, depth=1, no_single_branch=True)
            if body.ref:
                cloned.git.checkout(body.ref)
        except GitCommandError as exc:
            raise HTTPException(status_code=400, detail=f"git clone failed: {exc}") from exc

        source = Path(tmp) / body.subdirectory if body.subdirectory else Path(tmp)
        if not source.is_dir():
            raise HTTPException(
                status_code=400, detail=f"subdirectory {body.subdirectory!r} not found"
            )
        # A git repo commonly carries the same module twice — once bare and once
        # revision-stamped (foo.yang and foo@2022-06-20.yang) — and often under
        # several directories. Copying every path leaves the module list full
        # of duplicates, so keep one file per name@revision.
        copied = 0
        skipped_duplicates = 0
        seen: dict[str, Path] = {}
        for yang_file in sorted(source.rglob("*.yang")):
            info = parse_file(yang_file)
            if info is None:
                continue
            if info.key in seen:
                skipped_duplicates += 1
                continue
            seen[info.key] = yang_file
            # Name the copy canonically so a later import lands on the same file.
            target = f"{info.name}@{info.revision}.yang" if info.revision else f"{info.name}.yang"
            try:
                shutil.copy(yang_file, repo.path / target)
                copied += 1
            except OSError:
                continue
    modules = repo.modules(refresh=True)
    return {
        "copied": copied,
        "skipped_duplicates": skipped_duplicates,
        "module_count": len(modules),
    }


@router.post("/repositories/{slug}/remove-modules")
def remove_modules(slug: str, keys: list[str]) -> dict:
    try:
        removed = Repository.load(slug).remove_modules(keys)
    except StorageError as exc:
        raise _wrap(exc) from exc
    return {"removed": removed}


# --------------------------------------------------------------------------
# YANG sets
# --------------------------------------------------------------------------

@router.get("/yangsets")
def list_yangsets() -> list[dict]:
    return [
        {
            "slug": ys.slug,
            "name": ys.name,
            "repository": ys.repository,
            "module_count": len(ys.modules),
            "modified": ys.modified,
        }
        for ys in YangSet.all()
    ]


@router.post("/yangsets", status_code=201)
def create_yangset(body: S.YangSetCreate) -> dict:
    try:
        ys = YangSet.create(
            body.name, body.repository, [m.model_dump() for m in body.modules]
        )
    except StorageError as exc:
        raise _wrap(exc) from exc
    return {"slug": ys.slug, "name": ys.name, "module_count": len(ys.modules)}


@router.get("/yangsets/{slug}")
def get_yangset(slug: str) -> dict:
    try:
        ys = YangSet.load(slug)
    except StorageError as exc:
        raise _wrap(exc) from exc
    return asdict(ys)


@router.patch("/yangsets/{slug}")
def update_yangset(slug: str, body: S.YangSetUpdate) -> dict:
    try:
        ys = YangSet.load(slug)
        if body.name is not None:
            ys.name = body.name
        if body.modules is not None:
            ys.modules = [m.model_dump() for m in body.modules]
        ys.save()
    except StorageError as exc:
        raise _wrap(exc) from exc
    explorer.invalidate(ys.slug)
    return asdict(ys)


@router.delete("/yangsets/{slug}", status_code=204)
def delete_yangset(slug: str) -> None:
    try:
        YangSet.load(slug).delete()
    except StorageError as exc:
        raise _wrap(exc) from exc
    explorer.invalidate(slug)


def _unique_name(base: str) -> str:
    """A set name that does not collide with an existing one."""
    from ..core.storage import slugify

    existing = {ys.slug for ys in YangSet.all()}
    if slugify(base) not in existing:
        return base
    for n in range(2, 100):
        candidate = f"{base} {n}"
        if slugify(candidate) not in existing:
            return candidate
    return f"{base} {len(existing) + 1}"


def _build_set(name: str, repository: str, entries: list[dict]) -> dict:
    """Create a set, pull in its imports, and report whether it will parse."""
    yangset = YangSet.create(_unique_name(name), repository, entries)
    added = yangset.add_dependencies()
    explorer.invalidate(yangset.slug)
    return {
        "slug": yangset.slug,
        "name": yangset.name,
        "repository": yangset.repository,
        "module_count": len(yangset.modules),
        "dependencies_added": added,
        "validation": yangset.validate(),
    }


@router.post("/yangsets/from-modules", status_code=201)
def create_yangset_from_modules(body: S.YangSetFromModules) -> dict:
    """Turn an explicit module list into a set — e.g. a finished download.

    The download already knows exactly which modules were fetched, so asking
    the user to reselect them on another page is asking twice.
    """
    try:
        repo = Repository.load(body.repository)
    except StorageError as exc:
        raise _wrap(exc) from exc

    entries, skipped = [], []
    for name in body.modules:
        info = repo.find_module(name)
        if info is None:
            skipped.append(name)
            continue
        entries.append({"name": info.name, "revision": info.revision})

    if not entries:
        raise HTTPException(
            status_code=400,
            detail="none of those modules are in the repository",
        )
    try:
        result = _build_set(body.name, repo.slug, entries)
    except StorageError as exc:
        raise _wrap(exc) from exc
    result["skipped"] = skipped
    return result


@router.post("/yangsets/from-device", status_code=201)
def create_yangset_from_device(body: S.YangSetFromDevice) -> dict:
    """Build a set from a device's advertised capabilities.

    A capability list is a better set definition than anything assembled by
    hand: it pins the revision the device actually implements and carries the
    features and deviations it declares, which a repository cannot express.
    """
    try:
        device = Device.load(body.device)
        repo = Repository.load(body.repository)
        service = restconf_svc if body.transport == "restconf" else netconf_svc
        advertised = service.capabilities(device)["modules"]
    except Exception as exc:
        raise _wrap(exc) from exc

    wanted = set(body.modules) if body.modules else None
    entries, not_in_repo = [], []
    for module in advertised:
        name = module["name"]
        if wanted is not None and name not in wanted:
            continue
        # Prefer the exact revision the device claims; fall back to whatever
        # the repository holds under that name.
        info = repo.find_module(name, module.get("revision", "")) or repo.find_module(name)
        if info is None:
            not_in_repo.append(name)
            continue
        entry = {"name": info.name, "revision": info.revision}
        if body.include_features and module.get("features"):
            entry["features"] = module["features"]
        if module.get("deviations"):
            entry["deviations"] = module["deviations"]
        entries.append(entry)

    if not entries:
        raise HTTPException(
            status_code=400,
            detail=(
                "none of the modules this device advertises are in that "
                "repository — download them first"
            ),
        )
    try:
        result = _build_set(body.name, repo.slug, entries)
    except StorageError as exc:
        raise _wrap(exc) from exc
    result["not_in_repository"] = sorted(not_in_repo)
    return result


@router.get("/yangsets/{slug}/validate")
def validate_yangset(slug: str) -> dict:
    try:
        return YangSet.load(slug).validate()
    except StorageError as exc:
        raise _wrap(exc) from exc


@router.post("/yangsets/{slug}/resolve-dependencies")
def resolve_dependencies(slug: str) -> dict:
    try:
        ys = YangSet.load(slug)
        added = ys.add_dependencies()
    except StorageError as exc:
        raise _wrap(exc) from exc
    explorer.invalidate(ys.slug)
    return {"added": added, "modules": ys.modules, "validation": ys.validate()}


# --------------------------------------------------------------------------
# Explorer
# --------------------------------------------------------------------------

@router.get("/explore/{slug}/tree")
async def get_tree(
    slug: str,
    modules: str = Query("", description="Comma-separated module names"),
    refresh: bool = False,
) -> dict:
    module_list = [m for m in modules.split(",") if m] or None
    try:
        ys = YangSet.load(slug)
        parsed, flat = await run_in_threadpool(
            explorer.get_parsed, ys, module_list, refresh
        )
    except Exception as exc:
        raise _wrap(exc) from exc
    return {
        "yangset": {"slug": ys.slug, "name": ys.name},
        "modules": parsed.modules,
        "diagnostics": [asdict(d) for d in parsed.diagnostics],
        "stats": explorer.stats(parsed, flat),
    }


@router.get("/explore/{slug}/search")
async def search_tree(
    slug: str,
    q: str = "",
    modules: str = Query(""),
    nodetypes: str = Query(""),
    access: str = Query(""),
    limit: int = 200,
) -> dict:
    module_list = [m for m in modules.split(",") if m] or None
    try:
        ys = YangSet.load(slug)
        _parsed, flat = await run_in_threadpool(explorer.get_parsed, ys, module_list, False)
    except Exception as exc:
        raise _wrap(exc) from exc
    results = explorer.search(
        flat,
        q,
        nodetypes=[n for n in nodetypes.split(",") if n] or None,
        access=access or None,
        limit=limit,
    )
    return {"query": q, "count": len(results), "results": results}


@router.get("/explore/{slug}/node")
async def get_node(slug: str, xpath: str, modules: str = Query("")) -> dict:
    module_list = [m for m in modules.split(",") if m] or None
    try:
        ys = YangSet.load(slug)
        _, flat = await run_in_threadpool(explorer.get_parsed, ys, module_list, False)
    except Exception as exc:
        raise _wrap(exc) from exc
    node = explorer.node_by_xpath(flat, xpath)
    if node is None:
        raise HTTPException(status_code=404, detail=f"no node at {xpath!r}")
    return node


# --------------------------------------------------------------------------
# Devices
# --------------------------------------------------------------------------

@router.get("/devices")
def list_devices() -> list[dict]:
    return [d.redacted() for d in Device.all()]


@router.post("/devices", status_code=201)
def create_device(body: S.DeviceCreate) -> dict:
    try:
        device = Device.create(**body.model_dump())
    except StorageError as exc:
        raise _wrap(exc) from exc
    return device.redacted()


@router.get("/devices/{slug}")
def get_device(slug: str) -> dict:
    try:
        return Device.load(slug).redacted()
    except StorageError as exc:
        raise _wrap(exc) from exc


@router.patch("/devices/{slug}")
def update_device(slug: str, body: S.DeviceUpdate) -> dict:
    try:
        device = Device.load(slug)
        payload = {k: v for k, v in body.model_dump().items() if v is not None}
        # A redacted password coming back from the UI must not overwrite the
        # stored one.
        if payload.get("password") == "********":
            payload.pop("password")
        device.apply(payload)
        device.save()
    except StorageError as exc:
        raise _wrap(exc) from exc
    return device.redacted()


@router.delete("/devices/{slug}", status_code=204)
def delete_device(slug: str) -> None:
    try:
        Device.load(slug).delete()
    except StorageError as exc:
        raise _wrap(exc) from exc
    netconf_svc.close_session(slug)


@router.get("/devices/{slug}/protocols")
def device_protocols(slug: str) -> dict:
    try:
        device = Device.load(slug)
    except StorageError as exc:
        raise _wrap(exc) from exc
    return {
        proto: {
            k: v for k, v in asdict(device.resolve(proto)).items() if k != "password"
        }
        for proto in PROTOCOLS
    }


# --------------------------------------------------------------------------
# NETCONF
# --------------------------------------------------------------------------

@router.get("/netconf/{slug}/capabilities")
async def netconf_capabilities(slug: str) -> dict:
    try:
        device = Device.load(slug)
        return await run_in_threadpool(netconf_svc.capabilities, device)
    except Exception as exc:
        raise _wrap(exc) from exc


@router.get("/netconf/{slug}/datastores")
async def netconf_datastores(slug: str) -> dict:
    try:
        device = Device.load(slug)
        return {"datastores": await run_in_threadpool(netconf_svc.datastores, device)}
    except Exception as exc:
        raise _wrap(exc) from exc


@router.post("/netconf/{slug}/disconnect")
def netconf_disconnect(slug: str) -> dict:
    return {"closed": netconf_svc.close_session(slug)}


def _start_schema_download(
    slug: str, body: S.SchemaDownload, transport: str
) -> dict:
    """Start a background download. Returns immediately with a job to poll.

    Fetching schemas is one round trip per module, so a few hundred modules is
    several minutes. Running it inside the request would tie the work to the
    page that started it.

    The two transports do the same job and return the same shape, so the only
    thing that changes here is which service is asked.
    """
    service = restconf_svc if transport == "restconf" else netconf_svc
    try:
        device = Device.load(slug)
        repo = Repository.load(body.repository) if body.repository else None
    except StorageError as exc:
        raise _wrap(exc) from exc

    if not body.modules:
        raise HTTPException(status_code=400, detail="no modules selected")

    modules = list(body.modules)
    target = repo.name if repo else "memory"
    label = (
        f"{len(modules)} schema{'' if len(modules) == 1 else 's'} "
        f"from {device.name} → {target}"
    )
    # Anything already downloaded does not need fetching again when following
    # a dependency tree.
    already_have = {m.name for m in repo.modules()} if repo is not None else set()

    def run(handle) -> dict:
        handle.set_total(len(modules))
        # Both transports do something slow before the first module — NETCONF
        # opens a session, RESTCONF reads the YANG library — and it can take
        # seconds, so say so rather than sitting at 0%.
        opening = (
            f"Reading the YANG library from {device.name}\u2026"
            if transport == "restconf"
            else f"Connecting to {device.name}\u2026"
        )
        handle.set_progress(0, opening)

        def progress(name: str, done: int, total: int) -> None:
            # The total grows as imports are discovered, so it is reported
            # rather than fixed when the job starts.
            handle.set_total(total)
            handle.set_progress(done, name)

        result = service.download_schemas(
            device,
            modules,
            on_progress=progress,
            should_cancel=handle.cancelled,
            have=already_have,
        )
        for name, message in result["errors"].items():
            handle.record_error(name, message)

        saved = 0
        if repo is not None:
            for name, text in result["schemas"].items():
                (repo.path / f"{name}.yang").write_text(text)
                saved += 1
            repo.modules(refresh=True)

        downloaded = sorted(result["schemas"])
        failed = len(result["errors"])
        pulled_in = result.get("pulled_in", [])
        handle.set_progress(len(downloaded) + failed, "")
        aborted = result.get("aborted", "")

        message = f"Saved {saved} of {len(downloaded) + failed}"
        if pulled_in:
            message += (
                f" ({len(pulled_in)} pulled in as dependencies)"
            )
        if failed:
            message += f", {failed} failed"
        if aborted:
            message += f" — {aborted}"
        return {
            "downloaded": downloaded,
            "pulled_in": pulled_in,
            "saved_to_repository": saved,
            "repository": repo.slug if repo else "",
            # Carried so the UI can offer to fetch anything still missing
            # without asking which device it came from, or over which protocol.
            "device": device.slug,
            "transport": transport,
            "failed": failed,
            "aborted": aborted,
            "message": message,
        }

    job = registry.submit("download-schemas", label, run)
    return job.dict()


@router.post("/netconf/{slug}/download-schemas", status_code=202)
def netconf_download_schemas(slug: str, body: S.SchemaDownload) -> dict:
    """Download schemas over NETCONF, using <get-schema>."""
    return _start_schema_download(slug, body, "netconf")


@router.post("/restconf/{slug}/download-schemas", status_code=202)
def restconf_download_schemas(slug: str, body: S.SchemaDownload) -> dict:
    """Download schemas over RESTCONF, following the YANG library."""
    return _start_schema_download(slug, body, "restconf")


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------

@router.get("/jobs")
def list_jobs() -> list[dict]:
    return [job.dict() for job in registry.list()]


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id!r}")
    return job.dict()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    """Ask a job to stop. It halts at its next checkpoint, not instantly."""
    if registry.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id!r}")
    return {"cancelling": registry.cancel(job_id)}


@router.delete("/jobs")
def clear_finished_jobs() -> dict:
    return {"cleared": registry.clear_finished()}


# --------------------------------------------------------------------------
# RPC
# --------------------------------------------------------------------------

def _to_request(body: S.RpcBuild) -> rpc_core.RpcRequest:
    return rpc_core.RpcRequest(
        operation=body.operation,
        datastore=body.datastore,
        selections=[rpc_core.Selection(**s.model_dump()) for s in body.selections],
        namespaces=body.namespaces,
        with_defaults=body.with_defaults,
    )


@router.post("/rpc/build")
def build_rpc(body: S.RpcBuild) -> dict:
    try:
        return {"rpc_xml": rpc_core.build_rpc(_to_request(body))}
    except rpc_core.RpcError as exc:
        raise _wrap(exc) from exc


@router.post("/rpc/run")
async def run_rpc(body: S.RpcRun) -> dict:
    try:
        device = Device.load(body.device)
        rpc_xml = body.rpc_xml or rpc_core.build_rpc(_to_request(body))
        result = await run_in_threadpool(netconf_svc.run_rpc, device, rpc_xml)
    except Exception as exc:
        raise _wrap(exc) from exc
    result["rpc_xml"] = rpc_xml
    return result


# --------------------------------------------------------------------------
# RESTCONF
# --------------------------------------------------------------------------

def _plan(body: S.RestconfBuild):
    yangset = YangSet.load(body.yangset)
    return restconf_svc.plan(
        yangset,
        [s.model_dump() for s in body.selections],
        operation=body.operation,
        modules=body.modules or None,
    )


@router.post("/restconf/build")
async def build_restconf(body: S.RestconfBuild) -> dict:
    """Resolve selections into RESTCONF calls, without sending anything."""
    try:
        requests = await run_in_threadpool(_plan, body)
    except Exception as exc:
        raise _wrap(exc) from exc
    return {"requests": [r.dict() for r in requests], "count": len(requests)}


@router.post("/restconf/run")
async def run_restconf(body: S.RestconfRun) -> dict:
    """Build and execute. Several selections can mean several calls."""
    try:
        device = Device.load(body.device)
        requests = await run_in_threadpool(_plan, body)
    except Exception as exc:
        raise _wrap(exc) from exc

    if body.only is not None:
        if not 0 <= body.only < len(requests):
            raise HTTPException(status_code=400, detail=f"no request at index {body.only}")
        requests = [requests[body.only]]

    results = []
    for request in requests:
        outcome = await run_in_threadpool(restconf_svc.run, device, request)
        outcome["request"] = request.dict()
        results.append(outcome)

    return {
        "results": results,
        "ok": all(r["ok"] for r in results),
        "elapsed_ms": sum(r["elapsed_ms"] for r in results),
    }


@router.get("/restconf/{slug}/capabilities")
async def restconf_capabilities(slug: str) -> dict:
    """List the modules the device publishes in its YANG library.

    The RESTCONF counterpart of reading the NETCONF <hello>. It needs no
    session, and works on devices that do not speak NETCONF at all.
    """
    try:
        device = Device.load(slug)
        return await run_in_threadpool(restconf_svc.capabilities, device)
    except Exception as exc:
        raise _wrap(exc) from exc


@router.get("/restconf/{slug}/probe")
async def probe_restconf(slug: str) -> dict:
    """Check RESTCONF is reachable on a device and report its root."""
    try:
        device = Device.load(slug)
        return await run_in_threadpool(restconf_svc.probe, device)
    except Exception as exc:
        raise _wrap(exc) from exc
