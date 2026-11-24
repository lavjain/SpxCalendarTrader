"""FastAPI app: static files, JSON API, HTML pages and HTMX partials. Start with `uv run serve`."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import api, pages, partials
from app.core.schwab_api import SchwabAuthError, SchwabHTTPError
from app.core.store import Store
from app.settings import app_version, get_settings
from app.snapshots import SnapshotStore

STATIC_DIR = Path(__file__).parent / "static"


def create_app(db_path: str | None = None, snapshot_path: str | None = None) -> FastAPI:
    """App factory (uvicorn runs it with factory=True), so importing this module touches no files."""
    app = FastAPI(title="SPX Calendar Trader", version=app_version())
    app.state.store = Store(db_path or get_settings().db_path)
    app.state.store.init()
    app.state.snapshots = SnapshotStore(path=snapshot_path or get_settings().snapshot_path)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def revalidate_static(request: Request, call_next):
        """Scripts and styles are re-checked on every load (a cheap 304), so an edit is never hidden by the browser cache."""
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response
    app.include_router(api.router)
    app.include_router(partials.router)
    app.include_router(pages.router)

    @app.exception_handler(SchwabAuthError)
    async def auth_error(request: Request, exc: SchwabAuthError):
        return JSONResponse({"detail": f"Schwab login problem: {exc}"}, status_code=503)

    @app.exception_handler(SchwabHTTPError)
    async def http_error(request: Request, exc: SchwabHTTPError):
        return JSONResponse({"detail": f"Schwab request failed: {str(exc).splitlines()[0]}"}, status_code=502)

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    return app


def serve() -> None:
    import uvicorn
    uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=8000, reload=True,
                reload_dirs=["app"], env_file=".env")
