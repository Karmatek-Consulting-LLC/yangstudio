"""Fast, dependency-free extraction of YANG module metadata.

A full pyang parse of a large repository (Cisco native models run to thousands
of files and hundreds of MB) takes minutes, and listing a repository only needs
each file's header — so scan for that directly instead.

The scanner is a real tokenizer rather than a set of regexes, because YANG
headers contain comments, quoted strings with braces in them, and arguments
split across ``+`` concatenation. All three defeat pattern matching.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_WS = " \t\r\n"

# A statement's argument may be unquoted, single-quoted, double-quoted, or a
# '+'-concatenation of quoted parts.
_UNQUOTED_END = set(_WS) | {";", "{", "}"}


@dataclass
class ModuleInfo:
    """Header-level facts about a single YANG file."""

    name: str
    revision: str = ""
    namespace: str = ""
    prefix: str = ""
    kind: str = "module"          # "module" or "submodule"
    belongs_to: str = ""          # submodules only
    organization: str = ""
    description: str = ""
    yang_version: str = "1.0"
    imports: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    revisions: list[str] = field(default_factory=list)
    path: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable identifier: ``name@revision`` (revision may be empty)."""
        return f"{self.name}@{self.revision}" if self.revision else self.name


class _Scanner:
    """Minimal YANG lexer: yields (keyword, argument, depth, opens_block)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.end = len(text)

    def _skip_trivia(self) -> None:
        """Advance past whitespace and both comment styles."""
        while self.pos < self.end:
            ch = self.text[self.pos]
            if ch in _WS:
                self.pos += 1
            elif self.text.startswith("//", self.pos):
                nl = self.text.find("\n", self.pos)
                self.pos = self.end if nl == -1 else nl + 1
            elif self.text.startswith("/*", self.pos):
                close = self.text.find("*/", self.pos + 2)
                self.pos = self.end if close == -1 else close + 2
            else:
                return

    def _read_quoted(self, quote: str) -> str:
        """Read one quoted string, honouring backslash escapes in "..."."""
        self.pos += 1
        out: list[str] = []
        while self.pos < self.end:
            ch = self.text[self.pos]
            if ch == "\\" and quote == '"' and self.pos + 1 < self.end:
                nxt = self.text[self.pos + 1]
                out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
                self.pos += 2
                continue
            if ch == quote:
                self.pos += 1
                return "".join(out)
            out.append(ch)
            self.pos += 1
        return "".join(out)

    def _read_token(self) -> str | None:
        """Read a keyword or an argument (handling '+' concatenation)."""
        self._skip_trivia()
        if self.pos >= self.end:
            return None
        ch = self.text[self.pos]
        if ch in "\"'":
            parts = [self._read_quoted(ch)]
            # Concatenated strings: "a" + "b"
            while True:
                save = self.pos
                self._skip_trivia()
                if self.pos < self.end and self.text[self.pos] == "+":
                    self.pos += 1
                    self._skip_trivia()
                    if self.pos < self.end and self.text[self.pos] in "\"'":
                        parts.append(self._read_quoted(self.text[self.pos]))
                        continue
                self.pos = save
                break
            return "".join(parts)
        if ch in ";{}":
            self.pos += 1
            return ch
        start = self.pos
        while self.pos < self.end and self.text[self.pos] not in _UNQUOTED_END:
            self.pos += 1
        return self.text[start:self.pos] if self.pos > start else None

    def statements(self):
        """Yield ``(keyword, argument, depth)`` for every statement."""
        depth = 0
        pending: str | None = None       # keyword awaiting its argument
        pending_arg: str | None = None
        while True:
            tok = self._read_token()
            if tok is None:
                break
            if tok == "{":
                if pending:
                    yield pending, pending_arg or "", depth
                    pending, pending_arg = None, None
                depth += 1
            elif tok == "}":
                if pending:
                    yield pending, pending_arg or "", depth
                    pending, pending_arg = None, None
                depth = max(0, depth - 1)
            elif tok == ";":
                if pending:
                    yield pending, pending_arg or "", depth
                    pending, pending_arg = None, None
            elif pending is None:
                pending = tok
            elif pending_arg is None:
                pending_arg = tok
            # Extra tokens before ';'/'{' are malformed; ignore them.


# Revisions are ISO dates; anything else in that slot is not a revision.
_REV_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_text(text: str, path: str = "") -> ModuleInfo | None:
    """Extract header metadata from YANG source. Returns None if not a module."""
    scanner = _Scanner(text)
    info: ModuleInfo | None = None
    # Track the name of the import/include currently being described so that a
    # nested `revision-date` does not get mistaken for the module's revision.
    for keyword, arg, depth in scanner.statements():
        if info is None:
            if keyword in ("module", "submodule"):
                info = ModuleInfo(name=arg, kind=keyword, path=path)
                continue
            # Skip stray leading tokens; a real module statement comes first.
            continue

        if depth == 0:
            # Left the module block entirely.
            continue
        if depth != 1:
            # Only header statements (direct children of the module) matter.
            continue

        if keyword == "namespace":
            info.namespace = arg
        elif keyword == "prefix":
            info.prefix = arg
        elif keyword == "yang-version":
            info.yang_version = arg
        elif keyword == "organization" and not info.organization:
            info.organization = arg.strip()
        elif keyword == "description" and not info.description:
            info.description = arg.strip()
        elif keyword == "belongs-to":
            info.belongs_to = arg
        elif keyword == "import":
            if arg and arg not in info.imports:
                info.imports.append(arg)
        elif keyword == "include":
            if arg and arg not in info.includes:
                info.includes.append(arg)
        elif keyword == "revision" and _REV_RE.match(arg) and arg not in info.revisions:
            info.revisions.append(arg)

    if info is None:
        return None
    # YANG requires newest-first, but not every module in the wild complies.
    info.revisions.sort(reverse=True)
    info.revision = info.revisions[0] if info.revisions else ""
    return info


def parse_file(path: Path) -> ModuleInfo | None:
    """Quick-parse a ``.yang`` file, tolerating encoding problems."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ModuleInfo(name=path.stem, path=str(path), errors=[str(exc)])
    info = parse_text(text, path=str(path))
    if info is None:
        return None
    if not info.name:
        info.name = path.stem
        info.errors.append("module name missing from header")
    return info
