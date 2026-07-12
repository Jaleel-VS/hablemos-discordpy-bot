"""Generic game routes — one set of endpoints for every registered game.

    POST /api/games/{game_key}/start   -> start a new game (mode: daily|free)
    POST /api/games/{game_key}/guess   -> submit a guess, get updated view
    GET  /api/games                    -> list available games
    POST /api/games/{game_key}/stats   -> the caller's per-user daily stats

Identity is server-verified on every mutating call: the client sends its
access token and we resolve the real Discord user via ``users/@me`` rather than
trusting any client-sent id.

Game state travels round-trips in the request body but **sealed** (see
:mod:`sealed_state`) — the client holds an opaque, tamper-proof token, never
the raw state (which contains the answer). Each guess unseals, re-validates via
the engine, and re-seals. The client only ever sees ``sealed_state`` (opaque)
and ``view`` (answer-free until the game ends).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.discord_oauth import DiscordOAuthError, fetch_user
from app.games.base import GameError, Mode
from app.games.registry import available_games, get_engine
from app.games.sealed_state import StateSealError, seal, unseal

logger = logging.getLogger(__name__)


class StartRequest(BaseModel):
    access_token: str
    mode: Mode = "daily"
    # Optional, game-specific config (e.g. conjugation verb set / tenses).
    # Untrusted: each engine normalizes or ignores it.
    options: dict[str, Any] | None = None


class GuessRequest(BaseModel):
    access_token: str
    sealed_state: str  # opaque token from the previous response
    guess: str = ""
    # Request that an open-ended game end now (untimed conjugation practice).
    # Ignored by games without such a mode.
    finish: bool = False


class StatsRequest(BaseModel):
    access_token: str


def build_router(get_db, get_secret, discord_context: dict[str, int | None]) -> APIRouter:
    """Create the games router.

    ``get_db`` returns the Database or ``None`` when persistence is disabled
    (no ``DATABASE_URL``). ``get_secret`` returns the server secret used to
    seal state. ``discord_context`` carries optional channel/guild ids for
    result attribution (populated from the SDK in later phases).
    """
    router = APIRouter(prefix="/api/games")

    async def _verified_user_id(access_token: str) -> int:
        try:
            user = await fetch_user(access_token)
        except DiscordOAuthError:
            raise HTTPException(status_code=401, detail="Identidad no verificada")
        try:
            return int(user["id"])
        except (KeyError, ValueError):
            raise HTTPException(status_code=401, detail="Identidad no verificada")

    def _engine_or_404(game_key: str):
        engine = get_engine(game_key)
        if engine is None:
            raise HTTPException(status_code=404, detail="Juego no encontrado")
        return engine

    async def _persist_if_over(engine, game_key: str, user_id: int, state: dict) -> None:
        if not engine.is_over(state):
            return
        db = get_db()
        if db is None:
            return
        result = engine.result_payload(state)
        try:
            await db.record_result(
                game_key=game_key,
                user_id=user_id,
                mode=state.get("mode", "free"),
                won=bool(result.get("won")),
                puzzle_no=result.get("puzzle_no"),
                payload=result,
                channel_id=discord_context.get("channel_id"),
                guild_id=discord_context.get("guild_id"),
            )
        except Exception:  # noqa: BLE001 — never fail the request on a stats write
            logger.exception("Failed to persist result for game=%s user=%s", game_key, user_id)

    def _response(engine, state: dict) -> dict[str, Any]:
        return {"sealed_state": seal(get_secret(), state), "view": engine.client_view(state)}

    @router.get("")
    async def list_games() -> dict[str, Any]:
        return {"games": available_games()}

    @router.post("/{game_key}/start")
    async def start(game_key: str, body: StartRequest) -> dict[str, Any]:
        engine = _engine_or_404(game_key)
        # Verify identity ONCE, here, and bind it into the sealed state. The
        # seal is authenticated (Fernet), so the client can't forge/change it —
        # subsequent guesses trust the id in the state instead of re-hitting
        # Discord's users/@me on every answer (which dominated per-guess
        # latency: ~100ms hop vs. <1ms of actual game work).
        user_id = await _verified_user_id(body.access_token)
        # Pass the verified id to the engine (per the GameEngine contract — a
        # game may seed per-user daily state on it) AND bind it into the sealed
        # state so subsequent guesses trust it without re-hitting Discord.
        outcome = engine.new_game(mode=body.mode, user_id=str(user_id), options=body.options)
        outcome.state["_uid"] = user_id
        # Daily is a once-per-day fixed sequence: refuse a replay so a player
        # can't retry the same puzzle for a better score (or farm the honor
        # -system streak). Freeplay carries no puzzle_no and is never blocked.
        puzzle_no = outcome.state.get("puzzle_no")
        if body.mode == "daily" and isinstance(puzzle_no, int):
            db = get_db()
            if db is not None and await db.has_daily_result(
                game_key=game_key, user_id=user_id, puzzle_no=puzzle_no,
            ):
                raise HTTPException(
                    status_code=409, detail="Ya jugaste el reto diario de hoy.",
                )
        return _response(engine, outcome.state)

    @router.post("/{game_key}/guess")
    async def guess(game_key: str, body: GuessRequest) -> dict[str, Any]:
        engine = _engine_or_404(game_key)
        try:
            state = unseal(get_secret(), body.sealed_state)
        except StateSealError:
            raise HTTPException(status_code=400, detail="Estado de partida inválido")
        # Identity comes from the sealed state (bound at start) — no per-guess
        # Discord round trip. Fall back to a token verify only if it's absent
        # (e.g. an in-flight game started before this change deployed).
        state_uid = state.get("_uid")
        if isinstance(state_uid, int):
            user_id = state_uid
        else:
            user_id = await _verified_user_id(body.access_token)
            state["_uid"] = user_id
        try:
            outcome = engine.submit(state=state, guess=body.guess, finish=body.finish)
        except GameError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        await _persist_if_over(engine, game_key, user_id, outcome.state)
        return _response(engine, outcome.state)

    @router.post("/{game_key}/stats")
    async def stats(game_key: str, body: StatsRequest) -> dict[str, Any]:
        _engine_or_404(game_key)
        user_id = await _verified_user_id(body.access_token)
        db = get_db()
        if db is None:
            return {"games": 0, "wins": 0, "current_streak": 0, "max_streak": 0, "distribution": {}}
        return await db.get_stats(game_key=game_key, user_id=user_id)

    return router
