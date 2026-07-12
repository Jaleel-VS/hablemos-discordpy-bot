"""The game registry — the single place that knows which games exist.

Adding a game: import its engine and add it to ``_ENGINES``. Routes, auth, and
persistence are all generic over ``game_key`` and need no changes.
"""
from app.games.base import GameEngine
from app.games.wordle import WordleEngine

_ENGINES: dict[str, GameEngine] = {
    WordleEngine.key: WordleEngine(),
}


def get_engine(game_key: str) -> GameEngine | None:
    """Return the engine for ``game_key``, or ``None`` if unknown.

    ``None`` is normalized to a 404 at the route layer — callers don't guess.
    """
    return _ENGINES.get(game_key)


def available_games() -> list[dict[str, str]]:
    """List registered games for the frontend menu."""
    return [
        {"key": e.key, "display_name": e.display_name}
        for e in _ENGINES.values()
    ]
