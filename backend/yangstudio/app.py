"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .core.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    # Ask running jobs to stop so reloads and Ctrl-C are not held up waiting
    # on a download that has hundreds of RPCs left to make.
    from .services.jobs import registry

    cancelled = registry.cancel_all()
    if cancelled:
        print(f"Cancelling {cancelled} background job(s) on shutdown")


app = FastAPI(
    title="YANG Studio",
    lifespan=lifespan,
    description="A modern workbench for exploring and operating on YANG models.",
    version="0.1.0",
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "data_root": str(settings.data_root)}


def _find_static() -> Path | None:
    """Locate the built frontend, if there is one.

    Checked in order: an explicit override, then the layout of a source
    checkout. Returns None when the UI has not been built, in which case the
    API still serves normally.
    """
    if settings.static_dir:
        candidate = Path(settings.static_dir)
        return candidate if (candidate / "index.html").is_file() else None
    here = Path(__file__).resolve()
    for base in (here.parent.parent.parent, here.parent.parent):
        candidate = base / "frontend" / "dist"
        if (candidate / "index.html").is_file():
            return candidate
    return None


# Serve the built frontend when it exists, so a production run is one process.
_STATIC = _find_static()
if _STATIC is not None:
    app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        """Hand every non-API path to the SPA router."""
        candidate = _STATIC / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_STATIC / "index.html")


def main() -> None:
    import uvicorn

    uvicorn.run(
        "yangstudio.app:app",
        host=settings.host,
        port=settings.port,
        reload=bool(__import__("os").environ.get("YANGSTUDIO_RELOAD")),
    )


if __name__ == "__main__":
    main()
