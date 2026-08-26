"""Runtime configuration and on-disk layout for YANG Studio.

Storage is deliberately filesystem-first: YANG repositories are plain
directories of ``.yang`` files, so they can be version-controlled, rsync'd,
or hand-edited without going through the app.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


class Settings:
    """Process-wide settings, resolved from the environment once."""

    def __init__(self) -> None:
        self.data_root = Path(
            os.environ.get("YANGSTUDIO_DATA", Path.home() / ".yangstudio")
        ).expanduser()
        self.host = os.environ.get("YANGSTUDIO_HOST", "127.0.0.1")
        # Where the built frontend lives. Set explicitly in the container,
        # where the package is installed to site-packages and the repo-relative
        # path no longer resolves.
        self.static_dir = os.environ.get("YANGSTUDIO_STATIC", "")
        # 8000 is heavily contended on dev machines; default somewhere quieter.
        self.port = int(os.environ.get("YANGSTUDIO_PORT", "8420"))
        # Comma-separated list; the Vite dev server runs on 5173 by default.
        self.cors_origins = [
            o.strip()
            for o in os.environ.get(
                "YANGSTUDIO_CORS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if o.strip()
        ]

    @property
    def repos_dir(self) -> Path:
        return self.data_root / "repositories"

    @property
    def yangsets_dir(self) -> Path:
        return self.data_root / "yangsets"

    @property
    def devices_dir(self) -> Path:
        return self.data_root / "devices"

    @property
    def cache_dir(self) -> Path:
        return self.data_root / "cache"

    def ensure_dirs(self) -> None:
        for d in (self.repos_dir, self.yangsets_dir, self.devices_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
