"""The Spanish Wordle engine — implements the GameEngine protocol.

State shape (JSON-serializable, echoed by the client, re-validated each guess):
    {
      "mode": "daily" | "free",
      "answer": "<normalized secret>",   # server-only; never in client_view
      "max_guesses": 6,
      "puzzle_no": <int | null>,          # set for daily
      "rows": [                            # one per submitted guess
        {"guess": "<normalized>", "tiles": ["green", ...]}
      ],
      "status": "playing" | "won" | "lost",
      "date": "YYYY-MM-DD"                 # UTC date the game was created
    }

Random freeplay secrets are chosen with ``secrets.choice`` (not the disallowed
``random`` seeding paths) so no global RNG state is needed.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timezone
from typing import Any

from app.games.base import GameError, GuessOutcome, Mode
from app.games.wordle import daily as daily_mod
from app.games.wordle.normalize import WORD_LENGTH, is_valid_shape, normalize
from app.games.wordle.scorer import Tile, emoji_row, score
from app.games.wordle.words import ANSWERS, is_valid_guess

MAX_GUESSES = 6


def _today() -> date:
    return datetime.now(timezone.utc).date()


class WordleEngine:
    """Authoritative Spanish Wordle. Stateless across calls."""

    key = "wordle"
    display_name = "Wordle"

    # ── lifecycle ─────────────────────────────────────────────────────────

    def new_game(
        self, *, mode: Mode, user_id: str, options: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> GuessOutcome:
        today = _today()
        if mode == "daily":
            answer, puzzle_no = daily_mod.daily_answer(today)
        else:
            answer = secrets.choice(ANSWERS)
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
        self, *, state: dict[str, Any], guess: str, finish: bool = False,  # noqa: ARG002
    ) -> GuessOutcome:
        # Wordle has no open-ended mode; ``finish`` is part of the shared
        # contract but not meaningful here, so it is ignored.
        self._validate_state(state)
        if state["status"] != "playing":
            raise GameError("Esta partida ya terminó.")

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

        return {
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
        return view

    @staticmethod
    def _row_tiles(row: dict[str, Any]) -> list[Tile]:
        return [Tile(t) for t in row["tiles"]]

    @staticmethod
    def _validate_state(state: dict[str, Any]) -> None:
        """Guard against malformed/hostile state before trusting it."""
        if not isinstance(state, dict):
            raise GameError("Estado de partida inválido.")
        answer = state.get("answer")
        if not isinstance(answer, str) or not is_valid_shape(normalize(answer)):
            raise GameError("Estado de partida inválido.")
        if not isinstance(state.get("rows"), list):
            raise GameError("Estado de partida inválido.")
        if state.get("status") not in ("playing", "won", "lost"):
            raise GameError("Estado de partida inválido.")
