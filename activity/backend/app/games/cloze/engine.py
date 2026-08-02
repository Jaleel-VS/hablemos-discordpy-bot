"""The cloze (fill-in-the-blank) game — an untimed round implementing GameEngine.

The loop (the Clozemaster mechanic): show a sentence with one word blanked in
the learner's *target* language, plus the full sentence in the other language as
context; the player supplies the missing word — either by typing it or by
picking from four options — gets instant graded feedback, next card. A round is
a fixed number of cards (no clock).

Directions are two decks: ``target="es"`` blanks the Spanish word (English is
context) for Spanish learners; ``target="en"`` blanks the English word (Spanish
is context) for English learners. The player chooses at start.

Answer modes ride in the ``start`` options as ``answer_mode``:
* ``"choice"`` — 4-option multiple choice (answer + 3 precomputed distractors).
* ``"type"``   — free text, graded with the ñ-safe 3-way exact/close/wrong
  grader reused from the conjugation game (accents flagged, not failed).

Statelessness (same contract as the other games): the engine never holds a game
in memory. The full state — including each card's answer and the answered log —
round-trips through the client **sealed** (Fernet), so the client can neither
read a pending answer nor forge the score. Every ``submit`` unseals, grades
authoritatively, advances, and re-seals.

State shape::

    {
      "game": "cloze",
      "mode": "daily" | "free",
      "answer_mode": "choice" | "type",
      "target": "es" | "en",
      "difficulty": "beginner" | ... | null,
      "puzzle_no": <int | null>,          # set for daily
      "round_size": <int>,                # total cards this round
      "seq": <int>,                       # 0-based index of the current card
      "seed": "<str>",                    # option-shuffle seed (stable per run)
      "cards": [ {card as_state}, ... ],  # the whole round, precomputed
      "answered": [ {id, answer, given, result}, ... ],
      "correct": <int>,
      "streak": <int>,
      "best_streak": <int>,
      "status": "playing" | "over",
      "date": "YYYY-MM-DD"
    }

The daily round is a fixed, deterministic sequence shared by everyone, so the
per-card feedback withholds the answer in daily mode (anti-harvest) — the client
sees the exact/close/wrong flag but not the correct word until the end recap.
Freeplay reveals normally.
"""
from __future__ import annotations

import secrets
from datetime import UTC, date, datetime
from typing import Any

from app.games.base import GameError, GuessOutcome, Mode
from app.games.cloze import data as d
from app.games.conjugation.normalize import Match, grade

#: Cards per round (daily + default freeplay).
ROUND_SIZE = 10
#: Puzzle #1 epoch for the daily round number (matches the other games).
_EPOCH = date(2026, 1, 1)

_ANSWER_MODES = ("choice", "type")


def _now() -> datetime:
    return datetime.now(UTC)


def _resolve_answer_mode(options: dict[str, Any] | None) -> str:
    """Pick the answer mode from untrusted options, defaulting to choice."""
    if isinstance(options, dict):
        mode = options.get("answer_mode")
        if isinstance(mode, str) and mode in _ANSWER_MODES:
            return mode
    return "choice"


class ClozeEngine:
    """Authoritative untimed cloze round. Stateless across calls."""

    key = "cloze"
    display_name = "Cloze"

    # ── lifecycle ─────────────────────────────────────────────────────────

    def new_game(
        self, *, mode: Mode, user_id: str, options: dict[str, Any] | None = None,
    ) -> GuessOutcome:
        now = _now()
        today = now.date()
        # A per-run seed drives the deterministic option shuffle so the order a
        # card presents its choices is stable across the stateless round-trip
        # (grading is by value, but a stable order avoids flicker on re-render).
        seed = secrets.token_hex(8)

        if mode == "daily":
            config = d.daily_config()
            puzzle_no = (today - _EPOCH).days + 1
            answer_mode = _resolve_answer_mode(options)
            cards = d.deterministic_cards(config, seed=puzzle_no, count=ROUND_SIZE)
        else:
            config = d.resolve_config(options)
            puzzle_no = None
            answer_mode = _resolve_answer_mode(options)
            cards = d.random_cards(config, count=ROUND_SIZE)

        if not cards:
            raise GameError("No hay tarjetas disponibles.")

        state: dict[str, Any] = {
            "game": self.key,
            "mode": mode,
            "answer_mode": answer_mode,
            "target": config.target,
            "difficulty": config.difficulty,
            "puzzle_no": puzzle_no,
            "round_size": len(cards),
            "seq": 0,
            "seed": seed,
            "cards": [c.as_state() for c in cards],
            "answered": [],
            "correct": 0,
            "streak": 0,
            "best_streak": 0,
            "status": "playing",
            "date": today.isoformat(),
            "last": None,
        }
        return GuessOutcome(state=state, client_view=self.client_view(state))

    def submit(
        self, *, state: dict[str, Any], guess: str, finish: bool = False,
    ) -> GuessOutcome:
        self._validate_state(state)
        if state["status"] != "playing":
            raise GameError("Esta partida ya terminó.")

        # A cloze round has no clock; an explicit finish ends it immediately
        # (e.g. the player taps "Terminar" to bail out early).
        if finish:
            state["status"] = "over"
            state["last"] = None
            return GuessOutcome(state=state, client_view=self.client_view(state))

        card = self._current_card(state)
        result = grade(guess, card.answer)
        is_correct = result in (Match.EXACT, Match.CLOSE)

        state["answered"].append({
            "id": card.id,
            "answer": card.answer,
            "given": guess.strip(),
            "result": result.value,
        })
        if is_correct:
            state["correct"] += 1
            state["streak"] += 1
            state["best_streak"] = max(state["best_streak"], state["streak"])
        else:
            state["streak"] = 0

        # Feedback on the card just graded (client flashes this before the next
        # card animates in). Answer withheld in daily (see _client_last).
        state["last"] = {
            "result": result.value,
            "answer": card.answer,
            "given": guess.strip(),
            "context": card.context,
        }

        # Advance; end the round when we've served every card.
        state["seq"] += 1
        if state["seq"] >= state["round_size"]:
            state["status"] = "over"
        return GuessOutcome(state=state, client_view=self.client_view(state))

    def is_over(self, state: dict[str, Any]) -> bool:
        return state.get("status") == "over"

    # ── result card ───────────────────────────────────────────────────────

    def result_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        correct = int(state.get("correct", 0))
        answered = state.get("answered", [])
        total = len(answered)
        best_streak = int(state.get("best_streak", 0))

        header = "Cloze"
        if state.get("puzzle_no") is not None:
            header = f"Cloze #{state['puzzle_no']}"
        summary = f"{header} · {correct}/{total}"

        return {
            # Daily is a practice streak (completing the round counts), so it is
            # a "win" for streak/stats purposes.
            "won": True,
            "mode": state["mode"],
            "puzzle_no": state.get("puzzle_no"),
            "target": state.get("target"),
            "answer_mode": state.get("answer_mode"),
            # Reused by the shared stats machinery as the distribution bucket.
            "guesses_used": correct,
            "correct": correct,
            "total": total,
            "best_streak": best_streak,
            "score": f"{correct}/{total}",
            "grid": self._emoji_grid(answered),
            "summary": summary,
            "misses": [a for a in answered if a["result"] == Match.WRONG.value],
        }

    # ── helpers ───────────────────────────────────────────────────────────

    def client_view(self, state: dict[str, Any]) -> dict[str, Any]:
        """What the client may see. Excludes the pending answer while playing."""
        view: dict[str, Any] = {
            "game": self.key,
            "mode": state["mode"],
            "answer_mode": state.get("answer_mode", "choice"),
            "target": state.get("target"),
            "difficulty": state.get("difficulty"),
            "puzzle_no": state.get("puzzle_no"),
            "round_size": state.get("round_size", 0),
            "seq": state.get("seq", 0),
            "correct": state.get("correct", 0),
            "streak": state.get("streak", 0),
            "best_streak": state.get("best_streak", 0),
            "answered_count": len(state.get("answered", [])),
            "status": state["status"],
            "last": self._client_last(state),
        }
        if not self.is_over(state):
            view["prompt"] = self._current_card(state).prompt(seed=state.get("seed", ""))
        else:
            view["result"] = self.result_payload(state)
        return view

    def _client_last(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Per-card feedback, with the answer withheld in daily mode.

        The daily round is a fixed, deterministic sequence shared by everyone,
        so revealing each answer mid-run would let a player harvest the whole
        day's answers (mash junk, read ``answer``, restart, ace it). Daily play
        therefore gets the result flag (exact/close/wrong) but not ``answer`` —
        the correct words are disclosed only in the end-of-round recap.
        Freeplay reveals normally (there's nothing to game).
        """
        last = state.get("last")
        if last is None:
            return None
        if state.get("mode") == "daily":
            return {k: v for k, v in last.items() if k != "answer"}
        return last

    def _current_card(self, state: dict[str, Any]) -> d.Card:
        """Rebuild the current Card from stored state (answer included)."""
        seq = state["seq"]
        cards = state["cards"]
        if not isinstance(cards, list) or not (0 <= seq < len(cards)):
            raise GameError("Estado de partida inválido.")
        raw = cards[seq]
        if not isinstance(raw, dict):
            raise GameError("Estado de partida inválido.")
        return d._card_from_dict(raw)

    @staticmethod
    def _emoji_grid(answered: list[dict[str, Any]]) -> str:
        """Compact ✅/🟨/❌ block for the channel card, 10 per row, capped."""
        marks = {
            Match.EXACT.value: "✅",
            Match.CLOSE.value: "🟨",
            Match.WRONG.value: "❌",
        }
        cells = [marks.get(a["result"], "⬜") for a in answered[:40]]
        rows = ["".join(cells[i:i + 10]) for i in range(0, len(cells), 10)]
        return "\n".join(rows)

    @staticmethod
    def _validate_state(state: dict[str, Any]) -> None:
        """Guard against malformed/hostile state before trusting it."""
        if not isinstance(state, dict):
            raise GameError("Estado de partida inválido.")
        if state.get("game") != "cloze":
            raise GameError("Estado de partida inválido.")
        if state.get("status") not in ("playing", "over"):
            raise GameError("Estado de partida inválido.")
        if not isinstance(state.get("answered"), list):
            raise GameError("Estado de partida inválido.")
        cards = state.get("cards")
        if not isinstance(cards, list) or not cards:
            raise GameError("Estado de partida inválido.")
        seq = state.get("seq")
        if not isinstance(seq, int) or seq < 0:
            raise GameError("Estado de partida inválido.")
        # The current card (when still playing) must be a dict with a str answer.
        if state.get("status") == "playing":
            if seq >= len(cards):
                raise GameError("Estado de partida inválido.")
            current = cards[seq]
            if not isinstance(current, dict) or not isinstance(current.get("answer"), str):
                raise GameError("Estado de partida inválido.")
