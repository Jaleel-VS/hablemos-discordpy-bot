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

        # Daily is a fixed once-per-day sequence that feeds streaks, so a saved
        # token can't be finished on a later day (which would credit a streak
        # for a stale puzzle). Reject a daily submit once the state's date is no
        # longer today — mirrors Wordle's daily date gate. Freeplay has no date.
        if state.get("mode") == "daily" and state.get("date") != _now().date().isoformat():
            raise GameError("El reto diario de ese día ya expiró.")

        # A cloze round has no clock. Freeplay may be ended early via "Terminar"
        # (it's practice, no streak stakes). The DAILY, however, feeds streaks —
        # allowing an early finish would let a player bank a completed-daily win
        # (and streak bump) for a 0/0 or partial run, then never actually drill.
        # So a daily may only finish by answering every card; an early daily
        # finish is rejected and nothing is persisted (an abandoned daily simply
        # doesn't count today).
        if finish:
            if state.get("mode") == "daily" and state.get("seq", 0) < state.get("round_size", 0):
                raise GameError("Termina el reto diario para que cuente.")
            state["status"] = "over"
            state["last"] = None
            return GuessOutcome(state=state, client_view=self.client_view(state))

        # Reject an empty (non-finish) guess. Grading "" would count a card as
        # answered (wrong) and advance the round, which — chained — lets a
        # client walk a daily to completion without ever attempting an answer
        # (banking a persisted won=True, 0/N result + streak). Every real answer
        # (a typed word or a tapped option) is non-empty; the client only sends
        # "" via the finish path handled above.
        if not guess.strip():
            raise GameError("Escribe o elige una respuesta.")

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
            # The recap review list. Include both WRONG and CLOSE (accent) cards
            # so the learner sees the correct spelling of everything they didn't
            # nail — crucial in daily mode, where per-card feedback is withheld
            # during play (an accent miss otherwise never surfaces the correct
            # form). Each entry carries its ``result`` so the client can render
            # a CLOSE differently from an outright miss.
            "misses": [
                a for a in answered
                if a["result"] in (Match.WRONG.value, Match.CLOSE.value)
            ],
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
            view["prompt"] = self._current_card(state).prompt(
                seed=state.get("seed", ""),
                include_options=state.get("answer_mode") == "choice",
            )
        else:
            view["result"] = self.result_payload(state)
        return view

    def _client_last(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Per-card feedback, suppressed during daily play.

        The daily round is a fixed, deterministic sequence shared by everyone,
        and the backend is stateless (state round-trips as a sealed token). If
        daily feedback exposed anything about the just-graded card, a player
        could **replay the previous turn's token** and vary the guess to probe:
        in choice mode, three replays against the four options reveal the answer
        (watch which one flips the result flag), then submit the winner on the
        "real" branch. Withholding the *answer* alone doesn't close this — the
        result flag itself is the probing signal.

        So during daily play we return **no per-card feedback at all** (only the
        running score/streak, which leak nothing about the current card). The
        correct words — and which ones were missed — are disclosed only in the
        end-of-round recap, which is reachable solely by answering every card
        (an early daily finish is rejected). Freeplay reveals normally (it feeds
        no streak and there's nothing to game).

        This remains an honor-system boundary in the same sense the conjugation
        daily documents: the date→cards mapping is derivable from public code,
        so a determined player can still precompute answers offline. Closing
        that fully needs server-side per-guess attempt consumption, a cost we
        deliberately don't pay for a cosmetic streak. What this *does* close is
        the cheap in-client token-replay probe.
        """
        last = state.get("last")
        if last is None:
            return None
        if state.get("mode") == "daily":
            return None
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
        """Guard against malformed/hostile state before trusting it.

        The sealed state is authenticated, so a well-formed state can only come
        from us — but a *legacy* state, a truncated token, or a deliberately
        malformed one must fail with a clean :class:`GameError` (→ HTTP 400),
        never a raw ``KeyError``/``TypeError`` (→ HTTP 500). Every field the
        engine subsequently indexes without a ``.get`` default is checked here,
        including inside each card and each answered entry, so downstream code
        (``result_payload``, ``_emoji_grid``, ``_current_card``, ``options``)
        can trust the shape.
        """
        def bad() -> GameError:
            return GameError("Estado de partida inválido.")

        if not isinstance(state, dict):
            raise bad()
        if state.get("game") != "cloze":
            raise bad()
        if state.get("status") not in ("playing", "over"):
            raise bad()
        # mode / answer_mode are read via state[...] downstream (result_payload,
        # client_view), so they must be present and valid — not just truthy.
        if state.get("mode") not in ("daily", "free"):
            raise bad()
        if state.get("answer_mode") not in ("choice", "type"):
            raise bad()
        cards = state.get("cards")
        if not isinstance(cards, list) or not cards:
            raise bad()
        seq = state.get("seq")
        if not isinstance(seq, int) or seq < 0:
            raise bad()
        # Scoring counters must be well-typed ints — submit() does arithmetic on
        # them (``correct += 1``, ``max(best_streak, streak)``), so a hostile
        # string/None would raise a raw TypeError instead of a clean GameError.
        for key in ("correct", "streak", "best_streak"):
            if not isinstance(state.get(key), int):
                raise bad()
        # round_size is the loop bound for "round over"; it must match the deck
        # actually carried in state, or a tampered value could end early / never.
        if state.get("round_size") != len(cards):
            raise bad()
        # Every card must be well-shaped: str answer/cloze and a LIST of
        # distractors. ``distractors: null`` (or any non-list) would break
        # _card_from_dict's ``tuple(... for d in raw[...])`` and options() with a
        # raw TypeError; a non-str answer would break grading.
        for card in cards:
            if not isinstance(card, dict):
                raise bad()
            if not isinstance(card.get("answer"), str):
                raise bad()
            if not isinstance(card.get("cloze"), str):
                raise bad()
            if not isinstance(card.get("distractors"), list):
                raise bad()
        # The answered log can never exceed the cards served; and every entry
        # must be a dict carrying a str ``result`` (result_payload / _emoji_grid
        # index a["result"] on each), or a forged entry raises a raw error.
        answered = state.get("answered")
        if not isinstance(answered, list) or len(answered) > len(cards):
            raise bad()
        for entry in answered:
            if not isinstance(entry, dict) or not isinstance(entry.get("result"), str):
                raise bad()
        # While playing, the current card must be in range (submit indexes it).
        if state.get("status") == "playing" and seq >= len(cards):
            raise bad()
