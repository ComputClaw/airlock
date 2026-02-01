"""FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from airlock.api.admin import router as admin_router
from airlock.api.agent import router as agent_router
from airlock.api.health import router as health_router
from airlock.db import close_db, init_db

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle: init DB."""
    await init_db()

    print()
    print("=" * 56)
    print("  Airlock is running!")
    print("  Open http://localhost:9090 to configure")
    print("=" * 56)
    print()

    yield
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Airlock", version="0.1.0", lifespan=lifespan)

    app.include_router(health_router)
    app.include_router(agent_router)
    app.include_router(admin_router)

    if STATIC_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")

    @app.get("/")
    async def root():
        """Redirect root to web UI."""
        return RedirectResponse(url="/ui/")

    return app
