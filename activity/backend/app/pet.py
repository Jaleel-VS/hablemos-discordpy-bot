"""Pet feature for the Hablemos Activity.

One procedurally-drawn pixel critter per user, shown on the hub and game
summary screens.  Every player has one from the first visit: until they
customise it, :func:`default_pet` derives species and colour from their
Discord id (stable, nothing stored).  Mood is *derived* from play history at
request time — never stored.

Routes (all POST a body with ``access_token``, matching the site convention):

    POST /api/pet/me       — fetch the pet (stored or default) + mood/stats
    POST /api/pet/choose   — create or replace the pet (upsert)
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .discord_oauth import DiscordOAuthError, fetch_user

# Mirror of the frontend SPECIES tuple (model.ts).  Single source of truth on
# the Python side; keep in the same order as the TS constant.
SPECIES: tuple[str, ...] = (
    "blob", "drop", "orb", "sprout", "ghost",
    "bun", "star", "mochi", "cube", "pebble",
)

#: Mirror of the picker swatches (PetPicker.tsx), in the same order.
COLORS: tuple[str, ...] = (
    "#5fc9b5", "#f28c6a", "#8fa8ff", "#7ccf6a",
    "#c9a0ff", "#ffd166", "#ff8fab", "#9be7ff",
)

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_MAX_NAME = 20
_MAX_TOKEN = 512


def default_pet(user_id: int) -> dict[str, Any]:
    """The pet a player has before customising: stable per Discord id.

    Hashing (rather than ``user_id % n``) spreads sequential snowflakes
    across species and colours. Nothing is stored, so changing the picker
    later simply upserts over it. ``name`` is empty: the UI shows the
    species name, as it does for a customised pet left unnamed.
    """
    digest = hashlib.sha256(str(user_id).encode()).digest()
    return {
        "species": SPECIES[digest[0] % len(SPECIES)],
        "color": COLORS[digest[1] % len(COLORS)],
        "name": "",
    }


# ── validation ────────────────────────────────────────────────────────────────

def validate_choice(species: str, color: str, name: str) -> tuple[str, str, str]:
    """Validate and normalise a pet-choice payload.

    Returns ``(species, color, name)`` on success; raises
    ``HTTPException(400, ...)`` with a Spanish detail string on any violation.
    """
    if species not in SPECIES:
        raise HTTPException(
            status_code=400,
            detail=f"Especie inválida. Opciones: {', '.join(SPECIES)}",
        )
    if not _COLOR_RE.match(color):
        raise HTTPException(
            status_code=400,
            detail="Color inválido. Debe tener el formato #rrggbb.",
        )
    name = name.strip()
    if len(name) > _MAX_NAME:
        raise HTTPException(
            status_code=400,
            detail=f"El nombre no puede tener más de {_MAX_NAME} caracteres.",
        )
    return species, color, name


# ── mood derivation ───────────────────────────────────────────────────────────

def derive_mood(
    play_dates: list[date],
    today: date,
) -> tuple[str, int, bool]:
    """Derive mood, streak length, and whether the user played today.

    Pure function — no I/O.

    Returns ``(mood, streak_days, played_today)`` where ``mood`` is one of
    ``"idle" | "sleepy" | "waiting" | "happy"``.

    Mood rules:
    * No results ever → ``"idle"``.
    * Played today → streak ≥ 3 gives ``"happy"``, otherwise ``"idle"``.
    * Not today but yesterday → ``"waiting"`` (streak counts from yesterday).
    * Last play ≥ 7 days ago → ``"sleepy"``.
    * Otherwise → ``"idle"``.

    Streak: consecutive calendar days ending at the anchor (today if played,
    yesterday if not-today-but-yesterday).  A gap anywhere in the walk breaks
    the streak.
    """
    date_set = set(play_dates)

    if not date_set:
        return "idle", 0, False

    played_today = today in date_set
    yesterday = today - timedelta(days=1)

    if played_today:
        anchor = today
    elif yesterday in date_set:
        anchor = yesterday
    else:
        # Not today, not yesterday — check recency for sleepy/idle.
        most_recent = max(date_set)
        if (today - most_recent).days >= 7:
            return "sleepy", 0, False
        return "idle", 0, False

    # Walk back from anchor counting consecutive days.
    streak = 0
    cursor = anchor
    while cursor in date_set:
        streak += 1
        cursor -= timedelta(days=1)

    mood = ("happy" if streak >= 3 else "idle") if played_today else "waiting"

    return mood, streak, played_today


# ── zero-stats helper ─────────────────────────────────────────────────────────

def _zero_response(pet: dict[str, Any]) -> dict[str, Any]:
    """Response shape used when the database is unavailable."""
    return {
        "pet": pet,
        "mood": "idle",
        "streak_days": 0,
        "played_today": False,
        "games_this_week": 0,
        "favorite_game": None,
    }


# ── request models ────────────────────────────────────────────────────────────

class PetMeRequest(BaseModel):
    """Body of ``POST /api/pet/me``."""
    access_token: str


class PetChooseRequest(BaseModel):
    """Body of ``POST /api/pet/choose``."""
    access_token: str
    species: str
    color: str
    name: str = ""


# ── router ────────────────────────────────────────────────────────────────────

def build_pet_router(get_db) -> APIRouter:
    """Build the pet APIRouter.

    ``get_db`` is a zero-argument callable that returns the ``Database``
    instance or ``None`` when persistence is disabled (no ``DATABASE_URL``).
    """
    router = APIRouter(prefix="/api/pet")

    async def _verified_user_id(access_token: str) -> int:
        """Resolve and return the verified Discord user id."""
        try:
            user = await fetch_user(access_token)
        except DiscordOAuthError as exc:
            raise HTTPException(
                status_code=401, detail="Identidad no verificada"
            ) from exc
        try:
            return int(user["id"])
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=401, detail="Identidad no verificada"
            ) from exc

    def _today() -> date:
        # The SQL buckets play dates in UTC; the streak walk must use the
        # same calendar or a late-evening player sees tomorrow's mood.
        return datetime.now(UTC).date()

    async def _state(db, user_id: int, pet: dict[str, Any]) -> dict[str, Any]:
        activity = await db.pet_activity(user_id)
        mood, streak_days, played_today = derive_mood(activity["play_dates"], _today())
        return {
            "pet": pet,
            "mood": mood,
            "streak_days": streak_days,
            "played_today": played_today,
            "games_this_week": activity["games_this_week"],
            "favorite_game": activity["favorite_game"],
        }

    @router.post("/me")
    async def pet_me(body: PetMeRequest) -> dict[str, Any]:
        """Return the caller's pet and derived mood/stats.

        A player who never customised gets :func:`default_pet`, so ``pet`` is
        always present. With no ``DATABASE_URL`` (``get_db()`` is ``None``) the
        stats are zero.
        """
        user_id = await _verified_user_id(body.access_token)
        db = get_db()
        if db is None:
            return _zero_response(default_pet(user_id))
        stored = await db.get_pet(user_id)
        return await _state(db, user_id, stored if stored is not None else default_pet(user_id))

    @router.post("/choose")
    async def pet_choose(body: PetChooseRequest) -> dict[str, Any]:
        """Create or replace the caller's pet.

        Validates the payload, upserts into ``activity_pets``, and returns
        the same response shape as ``/me``.  When the database is unavailable,
        echoes the validated choice with zero stats so the dev UI can proceed.
        """
        species, color, name = validate_choice(body.species, body.color, body.name)
        user_id = await _verified_user_id(body.access_token)
        db = get_db()
        if db is None:
            return _zero_response({"species": species, "color": color, "name": name})
        return await _state(db, user_id, await db.upsert_pet(user_id, species, color, name))

    return router
