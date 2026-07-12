"""FastAPI entrypoint for the Hablemos Activity.

Serves two concerns from one origin (so Discord's proxy and same-origin
cookies stay simple):

* ``/api/*`` — the Activity backend (OAuth token exchange, verified identity,
  and, in later phases, game logic).
* everything else — the built Vite SPA (``frontend/dist``), with an
  SPA-history fallback to ``index.html``.

Inside Discord the SPA reaches these routes through the proxy prefix, e.g.
``fetch("/.proxy/api/token")``. The proxy strips ``/.proxy`` before it hits
this app, so the routes below are declared without that prefix.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Settings, load_settings
from .db import Database
from .discord_oauth import (
    DiscordOAuthError,
    close_http_client,
    exchange_code,
    fetch_user,
)
from .games.routes import build_router

logger = logging.getLogger(__name__)


class TokenRequest(BaseModel):
    """Body of ``POST /api/token`` — the OAuth2 code from ``authorize()``."""

    code: str


class TokenResponse(BaseModel):
    """Access token returned to the SPA so it can call ``authenticate()``."""

    access_token: str


class MeRequest(BaseModel):
    """Body of ``POST /api/me`` — the access token to verify."""

    access_token: str


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Accepts injected settings for testing."""
    cfg = settings or load_settings()

    # Configure logging so the app's own loggers actually emit. Without this,
    # uvicorn only sets up its own loggers and every ``logger.info`` in our
    # modules is dropped (root defaults to WARNING). Honor a LOG_LEVEL env var,
    # defaulting to INFO. Safe to call repeatedly (force=True re-applies).
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )

    # Database is optional: with no DATABASE_URL the app still serves the
    # handshake and games, but results/stats aren't persisted. Held in a
    # mutable holder so the games router can read it after lifespan startup.
    db_holder: dict[str, Database | None] = {"db": None}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if cfg.database_url:
            db = Database(cfg.database_url)
            try:
                await db.connect()
                db_holder["db"] = db
            except Exception:  # noqa: BLE001 — degrade gracefully, don't crash boot
                logger.exception("DB connect failed; running without persistence")
                db_holder["db"] = None
        else:
            logger.warning("DATABASE_URL not set — game persistence disabled")
        try:
            yield
        finally:
            await close_http_client()
            if db_holder["db"] is not None:
                await db_holder["db"].close()

    app = FastAPI(title="Hablemos Activity", version="0.1.0", lifespan=lifespan)

    app.include_router(
        build_router(
            get_db=lambda: db_holder["db"],
            get_secret=lambda: cfg.discord_client_secret,
            discord_context={"channel_id": None, "guild_id": None},
        )
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Liveness probe (also handy to confirm proxy routing works)."""
        return {"status": "ok", "environment": cfg.environment}

    @app.post("/api/token", response_model=TokenResponse)
    async def token(body: TokenRequest) -> TokenResponse:
        """Exchange the SPA's OAuth code for an access token, server-side."""
        try:
            access_token = await exchange_code(
                cfg.discord_client_id, cfg.discord_client_secret, body.code,
            )
        except DiscordOAuthError:
            raise HTTPException(status_code=502, detail="Discord token exchange failed")
        return TokenResponse(access_token=access_token)

    @app.post("/api/me")
    async def me(body: MeRequest) -> dict[str, str]:
        """Return the *verified* Discord identity for an access token.

        Phase 0 uses this to prove the end-to-end handshake by rendering the
        real user. Later phases reuse it to attribute game results.
        """
        try:
            user = await fetch_user(body.access_token)
        except DiscordOAuthError:
            raise HTTPException(status_code=502, detail="Failed to resolve Discord user")
        return user

    _mount_static(app, cfg)
    return app


def _mount_static(app: FastAPI, cfg: Settings) -> None:
    """Serve the built SPA with an index fallback for client-side routing.

    If the build output isn't present (e.g. running the API alone in dev), we
    skip mounting and log it rather than crashing — the API still works.
    """
    static_dir = cfg.static_dir
    index_file = os.path.join(static_dir, "index.html")
    if not os.path.isfile(index_file):
        logger.warning(
            "SPA build not found at %s — serving API only. Run the frontend "
            "build (npm run build) or set ACTIVITY_STATIC_DIR.",
            static_dir,
        )
        return

    # Hashed asset files (Vite emits them under /assets) get real static
    # serving; unknown paths fall back to index.html for SPA routing.
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}", response_model=None)
    async def spa_fallback(full_path: str) -> FileResponse | JSONResponse:
        # Never let the SPA fallback shadow the API namespace.
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = os.path.join(static_dir, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index_file)


# Module-level app for ``uvicorn app.main:app``. Guarded so that importing this
# module (e.g. in tests that call create_app with injected settings) doesn't
# require the real env to be present.
try:
    app = create_app()
except RuntimeError as exc:  # missing required env at import time
    logger.warning("App not created at import time: %s", exc)
    app = None
