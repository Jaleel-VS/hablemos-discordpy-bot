"""The Spanish conjugation game — a timed sprint implementing GameEngine.

The loop (the proven Conjuguemos mechanic): show verb + pronoun + tense, the
player types the conjugated form, get instant graded feedback, next prompt. Run
against the clock; score = how many correct before time runs out.

Statelessness (same contract as Wordle): the engine never holds a game in
memory. The full state — including the *current* question's answer and the log
of what's been answered — round-trips through the client **sealed** (Fernet),
so the client can neither read the pending answer nor forge the score. Every
``submit`` unseals, grades authoritatively, advances, and re-seals.

State shape::

    {
      "game": "conjugation",
      "mode": "daily" | "free",
      "duration": 60,
      "started_at": "<iso>",
      "deadline":   "<iso>",              # started_at + duration
      "puzzle_no":  <int | null>,         # set for daily
      "seq":        <int>,                # 0-based index of the current prompt
      "current":    {verb, english, tense, pronoun, expected},
      "answered":   [{verb, tense, pronoun, expected, given, result}, ...],
      "correct":    <int>,                # exact + close
      "streak":     <int>,                # current in-run streak
      "best_streak":<int>,
      "status":     "playing" | "over",
      "date":       "YYYY-MM-DD"
    }

Timing is server-authoritative: each submit compares ``now`` to ``deadline``.
Once the deadline passes, the game finalizes and further guesses are rejected.
The client also runs a visible countdown and, when it hits zero, sends one final
submit to flush the end state (the engine finalizes regardless of the guess).
"""
from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.games.base import GameError, GuessOutcome, Mode
from app.games.conjugation import data as d
from app.games.conjugation.normalize import Match, grade

#: Sprint length in seconds.
DURATION = 60
#: Grace after the deadline within which a just-submitted answer still counts
#: (covers request latency for an answer sent right as the clock hits zero).
_GRACE = timedelta(seconds=1.5)
#: Puzzle #1 epoch for the daily sprint number (matches Wordle's launch epoch).
_EPOCH = date(2026, 1, 1)


def _now() -> datetime:
    return datetime.now(UTC)


def _daily_config() -> d.Config:
    """Fixed daily config so everyone drills the same pools on a given day."""
    return d.Config(
        verb_set="high-frequency",
        tenses=list(d.TENSES),
        pronouns=[p for p in d.PRONOUNS if p != "vosotros"],
    )


def _deterministic_question(config: d.Config, *, seed: int, index: int) -> d.Question:
    """Reproducible question for daily mode.

    Derives verb/tense/pronoun indices from a hash of ``(seed, index)`` so the
    daily sprint yields the same ordered sequence for everyone without storing
    any RNG state across the stateless round-trip. Skips combos that lack stored
    forms by walking forward deterministically.
    """
    for bump in range(16):
        digest = hashlib.sha256(f"{seed}:{index}:{bump}".encode()).digest()
        verb = config.verbs[digest[0] % len(config.verbs)]
        tense = config.tenses[digest[1] % len(config.tenses)]
        pronoun = config.pronouns[digest[2] % len(config.pronouns)]
        q = d.make_question(verb, tense, pronoun)
        if q is not None:
            return q
    # Fallback: first valid combo (data would have to be broken to reach here).
    return d.pick_question(config)


class ConjugationEngine:
    """Authoritative timed conjugation sprint. Stateless across calls."""

    key = "conjugation"
    display_name = "Conjugación"

    # ── lifecycle ─────────────────────────────────────────────────────────

    def new_game(
        self, *, mode: Mode, user_id: str, options: dict[str, Any] | None = None,
    ) -> GuessOutcome:
        now = _now()
        today = now.date()
        if mode == "daily":
            # Daily is always the fixed timed sprint (it feeds streaks).
            config = _daily_config()
            puzzle_no = (today - _EPOCH).days + 1
            timed = True
            first = _deterministic_question(config, seed=puzzle_no, index=0)
        else:
            config = d.resolve_config(options)
            puzzle_no = None
            # Freeplay may be the 60s sprint or endless practice. Default to
            # timed so an empty/garbage options object still gets the sprint.
            timed = bool(options.get("timed", True)) if isinstance(options, dict) else True
            first = d.pick_question(config)

        state: dict[str, Any] = {
            "game": self.key,
            "mode": mode,
            "config": {
                "verb_set": config.verb_set,
                "tenses": config.tenses,
                "pronouns": config.pronouns,
            },
            "timed": timed,
            "duration": DURATION if timed else None,
            "started_at": now.isoformat(),
            # No deadline for untimed practice — it ends only on an explicit
            # finish action (or when the player leaves).
            "deadline": (now + timedelta(seconds=DURATION)).isoformat() if timed else None,
            "puzzle_no": puzzle_no,
            "seq": 0,
            "current": first.as_state(),
            "answered": [],
            "correct": 0,
            "streak": 0,
            "best_streak": 0,
            "status": "playing",
            "date": today.isoformat(),
        }
        return GuessOutcome(state=state, client_view=self.client_view(state))

    def submit(
        self, *, state: dict[str, Any], guess: str, finish: bool = False,
    ) -> GuessOutcome:
        self._validate_state(state)
        if state["status"] != "playing":
            raise GameError("Esta partida ya terminó.")

        # Explicit end (untimed practice "Terminar", or a client timer flush).
        # Finalize without grading this call's guess.
        if finish:
            # A timed game may only be finished by the end-of-timer flush, which
            # arrives at/after the deadline. Rejecting an early finish stops a
            # client from ending a timed daily instantly to bank a 0-answer
            # streak day; the untimed practice mode has no deadline and may
            # always finish on request.
            if state.get("timed", True) and _now() < self._deadline(state) - _GRACE:
                raise GameError("El reto cronometrado aún no ha terminado.")
            state["status"] = "over"
            state["last"] = None
            return GuessOutcome(state=state, client_view=self.client_view(state))

        # Server-authoritative clock (timed games only). Past the grace window,
        # finalize and ignore this guess (it's the client's end-of-timer flush).
        if state.get("timed", True) and _now() > self._deadline(state) + _GRACE:
            state["status"] = "over"
            state["last"] = None
            return GuessOutcome(state=state, client_view=self.client_view(state))

        current = self._config_question(state)
        result = grade(guess, current.expected)
        is_correct = result in (Match.EXACT, Match.CLOSE)

        state["answered"].append({
            "verb": current.verb,
            "tense": current.tense,
            "pronoun": current.pronoun,
            "expected": current.expected,
            "given": guess.strip(),
            "result": result.value,
        })
        if is_correct:
            state["correct"] += 1
            state["streak"] += 1
            state["best_streak"] = max(state["best_streak"], state["streak"])
        else:
            state["streak"] = 0

        # Feedback on the answer just graded (client flashes this before the
        # next prompt animates in).
        state["last"] = {
            "result": result.value,
            "expected": current.expected,
            "given": guess.strip(),
            "verb": current.verb,
            "pronoun": current.pronoun,
        }

        # Advance to the next prompt.
        state["seq"] += 1
        state["current"] = self._next_question(state).as_state()
        return GuessOutcome(state=state, client_view=self.client_view(state))

    def is_over(self, state: dict[str, Any]) -> bool:
        return state.get("status") == "over"

    # ── result card ───────────────────────────────────────────────────────

    def result_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        correct = int(state.get("correct", 0))
        answered = state.get("answered", [])
        total = len(answered)
        best_streak = int(state.get("best_streak", 0))

        header = "Conjugación"
        if state.get("puzzle_no") is not None:
            header = f"Conjugación #{state['puzzle_no']}"
        noun = "correcta" if correct == 1 else "correctas"
        summary = f"{header} · {correct} {noun}"

        return {
            # Daily is a practice streak (showing up counts), so completing the
            # sprint is a "win" for streak/stats purposes.
            "won": True,
            "mode": state["mode"],
            "puzzle_no": state.get("puzzle_no"),
            # Reused by the shared stats machinery as the distribution bucket.
            "guesses_used": correct,
            "correct": correct,
            "total": total,
            "best_streak": best_streak,
            "score": f"{correct}/{total}" if total else "0",
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
            "timed": state.get("timed", True),
            "duration": state.get("duration"),
            "deadline": state.get("deadline"),
            "puzzle_no": state.get("puzzle_no"),
            "correct": state.get("correct", 0),
            "streak": state.get("streak", 0),
            "best_streak": state.get("best_streak", 0),
            "answered_count": len(state.get("answered", [])),
            "status": state["status"],
            "last": self._client_last(state),
        }
        if not self.is_over(state):
            view["prompt"] = self._config_question(state).prompt()
        else:
            view["result"] = self.result_payload(state)
        return view

    def _client_last(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Per-answer feedback for the client, with the answer withheld in daily.

        The daily sprint is a fixed, deterministic sequence shared by everyone,
        so revealing each graded form mid-run would let a player harvest the
        whole day's answers (mash junk, read ``expected``, restart, ace it).
        Daily play therefore gets the result flag (exact/close/wrong) but not
        ``expected`` — the correct forms are disclosed only in the end-of-game
        recap. Freeplay/practice reveals normally (there's nothing to game).
        """
        last = state.get("last")
        if last is None:
            return None
        if state.get("mode") == "daily":
            return {k: v for k, v in last.items() if k != "expected"}
        return last

    def _config(self, state: dict[str, Any]) -> d.Config:
        cfg = state.get("config", {})
        return d.Config(
            verb_set=cfg.get("verb_set", "high-frequency"),
            tenses=cfg.get("tenses") or list(d.TENSES),
            pronouns=cfg.get("pronouns") or list(d.PRONOUNS),
        )

    def _config_question(self, state: dict[str, Any]) -> d.Question:
        """Rebuild the current Question from stored state (answer included)."""
        cur = state["current"]
        return d.Question(
            verb=cur["verb"],
            english=cur.get("english", ""),
            tense=cur["tense"],
            pronoun=cur["pronoun"],
            expected=cur["expected"],
        )

    def _next_question(self, state: dict[str, Any]) -> d.Question:
        config = self._config(state)
        if state["mode"] == "daily" and state.get("puzzle_no") is not None:
            return _deterministic_question(config, seed=state["puzzle_no"], index=state["seq"])
        return d.pick_question(config, avoid=self._config_question(state))

    @staticmethod
    def _deadline(state: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(state["deadline"])

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
        if state.get("game") != "conjugation":
            raise GameError("Estado de partida inválido.")
        if state.get("status") not in ("playing", "over"):
            raise GameError("Estado de partida inválido.")
        if not isinstance(state.get("answered"), list):
            raise GameError("Estado de partida inválido.")
        current = state.get("current")
        if not isinstance(current, dict) or not isinstance(current.get("expected"), str):
            raise GameError("Estado de partida inválido.")
        # A timed game must carry a parseable deadline; an untimed one has none.
        deadline = state.get("deadline")
        if deadline is not None:
            try:
                datetime.fromisoformat(deadline)
            except (TypeError, ValueError) as exc:
                raise GameError("Estado de partida inválido.") from exc
