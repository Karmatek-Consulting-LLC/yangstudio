"""Repositories and YANG sets: the two things a user actually manages.

A **repository** is a directory of ``.yang`` files — everything you have.
A **yangset** is a named selection of specific ``name@revision`` modules from
one repository — what you want to work with right now. Full parsing is
expensive, so you parse a set, never a whole repository.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import get_settings
from .quickparse import ModuleInfo, parse_file


class StorageError(Exception):
    """Raised for invalid names, missing objects, and conflicting writes."""


_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def slugify(name: str) -> str:
    """Turn a display name into a filesystem-safe identifier."""
    slug = _SLUG_RE.sub("-", name.strip()).strip("-.")
    if not slug or slug in (".", ".."):
        raise StorageError(f"{name!r} is not a usable name")
    return slug[:120]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Repositories
# --------------------------------------------------------------------------

@dataclass
class Repository:
    """A directory of YANG files plus a cached index of their headers."""

    slug: str
    name: str
    created: str = ""
    description: str = ""

    @property
    def path(self) -> Path:
        return get_settings().repos_dir / self.slug

    @property
    def _meta_path(self) -> Path:
        return self.path / ".yangstudio-repo.json"

    @property
    def _index_path(self) -> Path:
        return get_settings().cache_dir / f"repo-{self.slug}.index.json"

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def create(cls, name: str, description: str = "") -> Repository:
        repo = cls(slug=slugify(name), name=name, created=_now(), description=description)
        if repo.path.exists():
            raise StorageError(f"repository {repo.slug!r} already exists")
        repo.path.mkdir(parents=True)
        repo._write_meta()
        return repo

    @classmethod
    def load(cls, slug: str) -> Repository:
        path = get_settings().repos_dir / slugify(slug)
        if not path.is_dir():
            raise StorageError(f"no such repository: {slug!r}")
        meta_path = path / ".yangstudio-repo.json"
        meta = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text())
            except ValueError:
                meta = {}
        return cls(
            slug=path.name,
            name=meta.get("name", path.name),
            created=meta.get("created", ""),
            description=meta.get("description", ""),
        )

    @classmethod
    def all(cls) -> list[Repository]:
        root = get_settings().repos_dir
        return sorted(
            (cls.load(p.name) for p in root.iterdir() if p.is_dir()),
            key=lambda r: r.name.lower(),
        )

    def delete(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)
        self._index_path.unlink(missing_ok=True)

    def _write_meta(self) -> None:
        self._meta_path.write_text(
            json.dumps(
                {"name": self.name, "created": self.created, "description": self.description},
                indent=2,
            )
        )

    # -- contents ----------------------------------------------------------

    def yang_files(self) -> list[Path]:
        return sorted(p for p in self.path.rglob("*.yang") if p.is_file())

    def _fingerprint(self) -> str:
        """Cheap change-detector: count, newest mtime, and total size."""
        files = self.yang_files()
        if not files:
            return "empty"
        stats = [f.stat() for f in files]
        return f"{len(files)}:{max(int(s.st_mtime) for s in stats)}:{sum(s.st_size for s in stats)}"

    def modules(self, refresh: bool = False) -> list[ModuleInfo]:
        """Quick-parsed headers for every file, cached against a fingerprint."""
        fingerprint = self._fingerprint()
        if not refresh and self._index_path.is_file():
            try:
                cached = json.loads(self._index_path.read_text())
                if cached.get("fingerprint") == fingerprint:
                    return [ModuleInfo(**m) for m in cached["modules"]]
            except (ValueError, KeyError, TypeError):
                pass  # Corrupt or stale-format cache: rebuild it.

        modules: list[ModuleInfo] = []
        for path in self.yang_files():
            info = parse_file(path)
            if info is not None:
                modules.append(info)
        modules.sort(key=lambda m: (m.name.lower(), m.revision))
        self._index_path.write_text(
            json.dumps(
                {"fingerprint": fingerprint, "modules": [asdict(m) for m in modules]},
            )
        )
        return modules

    def find_module(self, name: str, revision: str = "") -> ModuleInfo | None:
        """Locate a module; with no revision, return the newest one."""
        matches = [m for m in self.modules() if m.name == name]
        if not matches:
            return None
        if revision:
            return next((m for m in matches if m.revision == revision), None)
        return max(matches, key=lambda m: m.revision)

    def add_file(self, filename: str, content: bytes) -> ModuleInfo | None:
        """Write one uploaded ``.yang`` file into the repository."""
        safe = Path(filename).name
        if not safe.endswith(".yang"):
            raise StorageError(f"{filename!r} is not a .yang file")
        target = self.path / safe
        target.write_bytes(content)
        return parse_file(target)

    def remove_modules(self, keys: list[str]) -> int:
        """Delete files by ``name@revision`` key. Returns the count removed."""
        wanted = set(keys)
        removed = 0
        for info in self.modules():
            if info.key in wanted or info.name in wanted:
                Path(info.path).unlink(missing_ok=True)
                removed += 1
        if removed:
            self.modules(refresh=True)
        return removed


# --------------------------------------------------------------------------
# YANG sets
# --------------------------------------------------------------------------

@dataclass
class YangSet:
    """A named, ordered selection of modules drawn from one repository."""

    slug: str
    name: str
    repository: str
    modules: list[dict] = field(default_factory=list)  # [{"name","revision"}]
    created: str = ""
    modified: str = ""

    @property
    def path(self) -> Path:
        return get_settings().yangsets_dir / f"{self.slug}.json"

    @classmethod
    def create(cls, name: str, repository: str, modules: list[dict] | None = None) -> YangSet:
        ys = cls(
            slug=slugify(name),
            name=name,
            repository=slugify(repository),
            modules=modules or [],
            created=_now(),
            modified=_now(),
        )
        if ys.path.exists():
            raise StorageError(f"yangset {ys.slug!r} already exists")
        Repository.load(ys.repository)  # Fail early if the repo is gone.
        ys.save()
        return ys

    @classmethod
    def load(cls, slug: str) -> YangSet:
        path = get_settings().yangsets_dir / f"{slugify(slug)}.json"
        if not path.is_file():
            raise StorageError(f"no such yangset: {slug!r}")
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            raise StorageError(f"yangset {slug!r} is corrupt: {exc}") from exc
        return cls(
            slug=path.stem,
            name=data.get("name", path.stem),
            repository=data.get("repository", ""),
            modules=data.get("modules", []),
            created=data.get("created", ""),
            modified=data.get("modified", ""),
        )

    @classmethod
    def all(cls) -> list[YangSet]:
        root = get_settings().yangsets_dir
        out = []
        for p in sorted(root.glob("*.json")):
            try:
                out.append(cls.load(p.stem))
            except StorageError:
                continue  # Skip corrupt entries rather than failing the list.
        return sorted(out, key=lambda y: y.name.lower())

    def save(self) -> None:
        self.modified = _now()
        self.path.write_text(json.dumps(asdict(self), indent=2))

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)

    def repo(self) -> Repository:
        return Repository.load(self.repository)

    def feature_map(self) -> dict[str, list[str]]:
        """Per-module enabled features, as advertised by a device.

        pyang treats a module absent from this map as "all features enabled",
        which is the right default for a set assembled by hand.
        """
        out: dict[str, list[str]] = {}
        for entry in self.modules:
            features = entry.get("features")
            # An explicit empty list is meaningful — the device implements none
            # of this module's features — so only a missing key means "all".
            if features is not None:
                out[entry["name"]] = list(features)
        return out

    def resolved_paths(self) -> list[Path]:
        """Filesystem paths for this set's modules, skipping any missing."""
        repo = self.repo()
        paths = []
        for entry in self.modules:
            info = repo.find_module(entry.get("name", ""), entry.get("revision", ""))
            if info and info.path:
                paths.append(Path(info.path))
        return paths

    def validate(self) -> dict:
        """Report anything that would stop this set parsing into one tree."""
        repo = self.repo()
        present: dict[str, ModuleInfo] = {}
        missing: list[dict] = []

        # A module may appear only once: two revisions of the same name cannot
        # coexist in a single schema, and pyang will pick one silently.
        seen_revisions: dict[str, set[str]] = {}
        for entry in self.modules:
            name = entry.get("name", "")
            seen_revisions.setdefault(name, set()).add(entry.get("revision", ""))
        conflicting = [
            {"module": name, "revisions": sorted(revs)}
            for name, revs in seen_revisions.items()
            if len(revs) > 1
        ]

        for entry in self.modules:
            info = repo.find_module(entry.get("name", ""), entry.get("revision", ""))
            if info is None:
                missing.append(entry)
            else:
                present[info.name] = info

        unresolved: list[dict] = []
        for info in present.values():
            for dep in info.imports + info.includes:
                if dep in present:
                    continue
                available = repo.find_module(dep) is not None
                unresolved.append(
                    {"required_by": info.name, "module": dep, "available_in_repo": available}
                )
        return {
            "ok": not missing and not unresolved and not conflicting,
            "missing": missing,
            "unresolved_dependencies": unresolved,
            "conflicting_revisions": conflicting,
        }

    def add_dependencies(self) -> int:
        """Pull in every import/include available in the repo, transitively."""
        repo = self.repo()
        have = {m.get("name") for m in self.modules}
        queue = list(have)
        added = 0
        while queue:
            info = repo.find_module(queue.pop())
            if info is None:
                continue
            for dep in info.imports + info.includes:
                if dep in have:
                    continue
                dep_info = repo.find_module(dep)
                if dep_info is None:
                    continue  # Not in this repo; validate() will report it.
                if any(m.get("name") == dep_info.name for m in self.modules):
                    continue  # Already pinned at some revision; do not add another.
                self.modules.append({"name": dep_info.name, "revision": dep_info.revision})
                have.add(dep)
                queue.append(dep)
                added += 1
        if added:
            self.modules.sort(key=lambda m: m["name"].lower())
            self.save()
        return added
