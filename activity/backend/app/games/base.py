"""The game engine contract shared by every single-player word game.

Adding a new game means implementing :class:`GameEngine` and registering it
in ``registry.py`` — no new routes, no changes to auth, persistence, or the
results-posting pipeline. Wordle is the first implementation.

Design notes:
* The engine is **stateless** — it never holds a game in memory. State is a
  plain JSON-serializable ``dict`` that the client echoes back on each guess,
  and the server re-validates every time. This keeps the backend horizontally
  scalable and survives restarts for free.
* The **answer never leaves the server** in ``client_view`` until the game is
  over. ``submit`` is authoritative: the client cannot cheat by inspecting the
  payload.
* ``mode`` is either ``"daily"`` (deterministic secret by date, counts toward
  streaks, eligible for channel posting) or ``"free"`` (random, unlimited, no
  streaks).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

Mode = Literal["daily", "free"]


class GameError(Exception):
    """Raised for invalid input (bad guess, game already over, etc.).

    Carries a user-safe message; the route layer turns it into an HTTP 400.
    """


@dataclass(frozen=True)
class GuessOutcome:
    """Result of applying one guess: the new state plus what the client sees."""

    state: dict[str, Any]
    client_view: dict[str, Any]


@runtime_checkable
class GameEngine(Protocol):
    """Contract every game module implements.

    Implementations must be pure with respect to ``state`` (no hidden mutation
    of module globals beyond read-only word lists), so the same state always
    produces the same result.
    """

    #: Stable identifier used in routes, the DB ``game_key`` column, and the
    #: frontend registry. Lowercase, no spaces (e.g. ``"wordle"``).
    key: str

    #: Human-facing name for menus and result cards (e.g. ``"Wordle"``).
    display_name: str

    def new_game(
        self, *, mode: Mode, user_id: str, options: dict[str, Any] | None = None,
    ) -> GuessOutcome:
        """Start a new game. Returns the initial state + client view.

        ``user_id`` is the verified Discord id — used to seed per-user daily
        state if a game wants it (Wordle keys the daily secret on date only,
        so it ignores this, but other games may not).

        ``options`` is optional, game-specific configuration from the client
        (e.g. the conjugation game's chosen verb set / tenses / pronouns for
        freeplay). Engines must treat it as untrusted and normalize/ignore it;
        Wordle ignores it entirely.
        """
        ...

    def submit(
        self, *, state: dict[str, Any], guess: str, finish: bool = False,
    ) -> GuessOutcome:
        """Apply one guess to ``state`` (authoritatively) and return the next.

        ``finish`` requests that the game end now without grading this call
        (used by games with an untimed/open-ended mode — e.g. the conjugation
        sprint's "Terminar" button). Games without such a mode ignore it.

        Raises :class:`GameError` on invalid input. Must be safe against
        arbitrary/hostile ``state`` and ``guess`` — never trust the client.
        """
        ...

    def is_over(self, state: dict[str, Any]) -> bool:
        """Whether the game has ended (win or loss)."""
        ...

    def result_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        """Shareable summary for persistence + the channel result card.

        Called only when :meth:`is_over` is true. Returns a JSON-serializable
        dict (e.g. emoji grid, guess count, win flag). This is what the Phase 2
        bot poller renders, so it must be self-contained and game-agnostic in
        shape where practical (include ``won`` and a human ``summary``).
        """
        ...
