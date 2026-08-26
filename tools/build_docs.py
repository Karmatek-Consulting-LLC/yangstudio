#!/usr/bin/env python3
"""Generate the documentation site into docs/.

The output is plain static HTML with no build step, which is what Cloudflare
Pages serves directly. This script exists so the chrome — head, top bar, side
navigation, footer — is written once rather than copied into every page.

    python3 tools/build_docs.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"

SITE = "YANG Studio"
REPO = "https://github.com/Karmatek-Consulting-LLC/yangstudio"
IMAGE = "ghcr.io/karmatek-consulting-llc/yangstudio"

# (slug, title, nav section). Slug "index" becomes the site root.
PAGES: list[tuple[str, str, str]] = [
    ("index", "Overview", "Start"),
    ("getting-started", "Getting started", "Start"),
    ("concepts", "YANG concepts", "Start"),
    ("netconf", "NETCONF", "Protocols"),
    ("restconf", "RESTCONF", "Protocols"),
    ("deploy", "Deploying", "Operate"),
    ("api", "HTTP API", "Operate"),
]

LOGO = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="m7 9 3 3-3 3"/>'
    '<path d="M13 15h4"/></svg>'
)
GH = (
    '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 '
    '3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53'
    '-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72'
    '1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15'
    '-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 '
    '2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29'
    '.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58'
    '-8-8-8Z"/></svg>'
)


def nav_html(current: str) -> str:
    """Side navigation, grouped by section, marking the current page."""
    out, seen = [], None
    for slug, title, section in PAGES:
        if section != seen:
            out.append(f"      <h4>{section}</h4>")
            seen = section
        href = "/" if slug == "index" else f"/{slug}"
        cur = ' aria-current="page"' if slug == current else ""
        out.append(f'      <a href="{href}"{cur}>{title}</a>')
    return "\n".join(out)


SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🌲</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Literata:opsz,wght@7..72,400;7..72,600;7..72,700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<link rel="stylesheet" href="/assets/site.css">
</head>
<body>

<header class="topbar">
  <a class="brand" href="/">{logo} {site}</a>
  <nav>
    <a href="/getting-started">Get started</a>
    <a href="/concepts">Concepts</a>
    <a href="/deploy">Deploy</a>
    <a class="gh" href="{repo}">{gh} GitHub</a>
  </nav>
</header>

<div class="shell">
  <aside class="sidenav">
{nav}
  </aside>
  <main>
{body}
    <footer class="site">
      <span>Apache 2.0</span>
      <a href="{repo}">Source</a>
      <a href="{image_url}">Container image</a>
      <span>Examples captured from a Cisco IOS-XE device.</span>
    </footer>
  </main>
</div>

</body>
</html>
"""


def render(slug: str, title: str, description: str, body: str) -> str:
    full = title if slug == "index" else f"{title} · {SITE}"
    return SHELL.format(
        title=full,
        description=description,
        site=SITE,
        logo=LOGO,
        gh=GH,
        repo=REPO,
        image_url=f"{REPO}/pkgs/container/yangstudio",
        nav=nav_html(slug),
        body=body,
    )


def figure(name: str, caption: str, wide: bool = False) -> str:
    cls = ' class="wide"' if wide else ""
    return (
        f'<figure{cls}><img src="/img/{name}.png" alt="{caption}" loading="lazy" '
        f'width="3200" height="1826"><figcaption>{caption}</figcaption></figure>'
    )


def write(slug: str, title: str, description: str, body: str) -> None:
    path = OUT / f"{slug}.html"
    path.write_text(render(slug, title, description, body))
    print(f"  {path.relative_to(ROOT)}  {len(path.read_text()) // 1024}KB")


def main() -> None:
    from docs_content import build          # noqa: PLC0415

    OUT.mkdir(exist_ok=True)
    for slug, title, description, body in build(figure, IMAGE, REPO):
        write(slug, title, description, body)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
