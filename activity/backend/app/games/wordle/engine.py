"""Engine updates for W1–W5: learning card, FREE_ANSWERS, typed errors, freeplay hint."""
from __future__ import annotations

import json
import secrets
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.games.base import GameError, GuessOutcome, Mode
from app.games.wordle import daily as daily_mod
from app.games.wordle.normalize import WORD_LENGTH, is_valid_shape, normalize
from app.games.wordle.scorer import Tile, emoji_row, score
from app.games.wordle.words import FREE_ANSWERS, is_valid_guess

MAX_GUESSES = 6

# Derived at view/result time — never stored in state.
_LEXICON_PATH = Path(__file__).resolve().parent.parent / "data" / "wordle_lexicon.json"


@lru_cache(maxsize=1)
def _lexicon() -> dict[str, Any]:
    """Load the lexicon once; returns {} if file not yet generated."""
    if not _LEXICON_PATH.exists():
        return {}
    try:
        return json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _learning_card(answer: str) -> dict[str, Any] | None:
    """Return the lexicon entry for *answer*, or None if missing."""
    return _lexicon().get(answer) or None


def _today() -> date:
    return datetime.now(UTC).date()


class WordleEngine:
    """Authoritative Spanish Wordle. Stateless across calls."""

    key = "wordle"
    display_name = "Wordle"

    # ── lifecycle ─────────────────────────────────────────────────────────

    def new_game(
        self, *, mode: Mode, user_id: str, options: dict[str, Any] | None = None,
    ) -> GuessOutcome:
        today = _today()
        if mode == "daily":
            answer, puzzle_no = daily_mod.daily_answer(today)
        else:
            answer = secrets.choice(FREE_ANSWERS)
            puzzle_no = None

        state: dict[str, Any] = {
            "mode": mode,
            "answer": answer,
            "max_guesses": MAX_GUESSES,
            "puzzle_no": puzzle_no,
            "rows": [],
            "status": "playing",
            "date": today.isoformat(),
        }
        return GuessOutcome(state=state, client_view=self.client_view(state))

    def submit(
        self, *, state: dict[str, Any], guess: str, finish: bool = False, action: str = "answer",
    ) -> GuessOutcome:
        # Wordle has no open-ended mode; ``finish`` is part of the shared
        # contract but not meaningful here, so it is ignored.
        self._validate_state(state)
        if state["status"] != "playing":
            raise GameError("Esta partida ya terminó.")
        # Daily only playable on its creation date. Prevents save-token-then-
        # finish-later abuse and ensures compute_streak() sees consecutive dates.
        if state.get("mode") == "daily" and state.get("date") != _today().isoformat():
            raise GameError("El reto diario de hoy ya no está disponible.")

        normalized = normalize(guess)
        if not is_valid_shape(normalized):
            raise GameError(f"La palabra debe tener {WORD_LENGTH} letras.")
        if not is_valid_guess(normalized):
            raise GameError("Esa palabra no está en la lista.")

        answer = state["answer"]
        tiles = score(normalized, answer)
        rows = state["rows"]
        rows.append({"guess": normalized, "tiles": [t.value for t in tiles]})

        if normalized == answer:
            state["status"] = "won"
        elif len(rows) >= state["max_guesses"]:
            state["status"] = "lost"

        return GuessOutcome(state=state, client_view=self.client_view(state))

    def is_over(self, state: dict[str, Any]) -> bool:
        return state.get("status") in ("won", "lost")

    # ── result card ───────────────────────────────────────────────────────

    def result_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        won = state["status"] == "won"
        guesses_used = len(state["rows"])
        score_str = f"{guesses_used}/{state['max_guesses']}" if won else f"X/{state['max_guesses']}"
        grid = "\n".join(emoji_row(self._row_tiles(r)) for r in state["rows"])

        header = "Wordle"
        if state.get("puzzle_no") is not None:
            header = f"Wordle #{state['puzzle_no']}"
        summary = f"{header} {score_str}"

        payload: dict[str, Any] = {
            "won": won,
            "mode": state["mode"],
            "puzzle_no": state.get("puzzle_no"),
            "guesses_used": guesses_used,
            "max_guesses": state["max_guesses"],
            "score": score_str,
            "grid": grid,
            "summary": summary,
            # The answer is safe to include only now that the game is over.
            "answer": state["answer"],
        }

        # W1: learning card derived from lexicon, only on game over.
        card = _learning_card(state["answer"])
        if card is not None:
            payload["learning_card"] = card

        return payload

    # ── helpers ───────────────────────────────────────────────────────────

    def client_view(self, state: dict[str, Any]) -> dict[str, Any]:
        """What the client may see. Excludes the answer until the game ends."""
        view: dict[str, Any] = {
            "game": self.key,
            "mode": state["mode"],
            "max_guesses": state["max_guesses"],
            "word_length": WORD_LENGTH,
            "puzzle_no": state.get("puzzle_no"),
            "rows": state["rows"],
            "status": state["status"],
        }
        if self.is_over(state):
            view["result"] = self.result_payload(state)
        elif state.get("mode") == "free" and len(state["rows"]) >= 3:
            # W4: after 3 non-winning guesses, freeplay gets a hint derived at
            # view time from the lexicon. Never stored in state; never in daily.
            card = _learning_card(state["answer"])
            if card is not None:
                view["hint"] = {"pos": card.get("pos", ""), "en": card.get("en", "")}
        return view

    @staticmethod
    def _row_tiles(row: dict[str, Any]) -> list[Tile]:
        return [Tile(t) for t in row["tiles"]]

    @staticmethod
    def _validate_state(state: dict[str, Any]) -> None:
        """Guard against malformed/hostile state before trusting it.

        A sealed token can only carry state *we* produced, but schema evolution
        or a secret rotation can surface an old/foreign shape — so every field
        the rest of ``submit``/``result_payload`` indexes into is checked here,
        turning a bad shape into a clean 400 rather than a later KeyError.
        """
        if not isinstance(state, dict):
            raise GameError("Estado de partida inválido.")
        answer = state.get("answer")
        if not isinstance(answer, str) or not is_valid_shape(normalize(answer)):
            raise GameError("Estado de partida inválido.")
        if state.get("status") not in ("playing", "won", "lost"):
            raise GameError("Estado de partida inválido.")
        max_guesses = state.get("max_guesses")
        if not isinstance(max_guesses, int) or max_guesses <= 0:
            raise GameError("Estado de partida inválido.")
        rows = state.get("rows")
        if not isinstance(rows, list) or len(rows) > max_guesses:
            raise GameError("Estado de partida inválido.")
        _tiles = {t.value for t in Tile}
        for row in rows:
            if not isinstance(row, dict):
                raise GameError("Estado de partida inválido.")
            tiles = row.get("tiles")
            if not isinstance(row.get("guess"), str) or not isinstance(tiles, list):
                raise GameError("Estado de partida inválido.")
            if any(t not in _tiles for t in tiles):
                raise GameError("Estado de partida inválido.")
