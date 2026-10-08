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
      "timed": true | false,
      "duration": 60 | null,
      "started_at": "<iso>",
      "deadline":   "<iso>",              # started_at + duration (timed only)
      "puzzle_no":  <int | null>,         # set for daily
      "seq":        <int>,                # 0-based index of the current prompt
      "config":     {verb_set, tenses, pronouns, strict, variants, items,
                     verbs_override},
      "current":    {verb, english, tense, pronoun, shown, expected},
      "answered":   [{verb, tense, pronoun, expected, given, result}, ...],
      "correct":    <int>,                # exact; close counts only when !strict
      "streak":     <int>,                # current in-run streak
      "best_streak":<int>,
      "skipped":    <int>,                # number of skipped prompts
      "close":      <int>,                # number of close answers
      "awaiting_retry": false,            # true after wrong/close in untimed free
      "retry_attempts": <int>,            # failed retries since awaiting_retry=true
      "status":     "playing" | "over",
      "last":       {result, given, verb, pronoun, tense, expected?, note?, row?},
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

#: Human-readable labels for the known verb sets. Unknown keys are title-cased.
SET_LABELS: dict[str, str] = {
    "high-frequency": "High Frequency",
    "regular-ar": "Regular -AR",
    "regular-er-ir": "Regular -ER/-IR",
    "irregulars": "Irregulars",
    "stem-changers": "Stem-Changers",
    "go-verbs": "Go-Verbs",
    "strong-preterite": "Strong Preterite",
    "spelling-changers": "Spelling-Changers",
    "accent-shifters": "Accent Shifters (actúo, reúno)",
}

_VALID_ACTIONS = {"answer", "skip", "retry"}
#: After this many failed retries in retry mode, advance anyway.
_MAX_RETRY_ATTEMPTS = 2


def _now() -> datetime:
    return datetime.now(UTC)


def daily_config() -> d.Config:
    """Fixed daily config so everyone drills the same pools on a given day.

    Tenses are pinned explicitly so that adding new tenses to the JSON file
    does NOT change the daily sequence — new tenses only appear after being
    deliberately added to this list.
    """
    return d.Config(
        verb_set="high-frequency",
        tenses=["presente", "pretérito", "imperfecto", "futuro"],
        pronouns=[p for p in d.PRONOUNS if p != "vosotros"],
        strict=False,
        variants=False,
        items=0,
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
            config = daily_config()
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
            "config": config.as_state(),
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
            "skipped": 0,
            "close": 0,
            "awaiting_retry": False,
            "retry_attempts": 0,
            "status": "playing",
            "date": today.isoformat(),
        }
        return GuessOutcome(state=state, client_view=self.client_view(state))

    def submit(
        self,
        *,
        state: dict[str, Any],
        guess: str,
        finish: bool = False,
        action: str = "answer",
    ) -> GuessOutcome:
        self._validate_state(state)
        if state["status"] != "playing":
            raise GameError("Esta partida ya terminó.")

        # Validate action.
        if action not in _VALID_ACTIONS:
            raise GameError(f"Acción inválida: {action!r}.")

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

        config = self._config(state)
        current = d.Question.from_state(state["current"])
        timed = state.get("timed", True)
        awaiting_retry = bool(state.get("awaiting_retry", False))

        # ── skip ──────────────────────────────────────────────────────────
        if action == "skip":
            if awaiting_retry:
                raise GameError("No puedes saltar mientras esperas el reintento.")
            state["answered"].append({
                "verb": current.verb,
                "tense": current.tense,
                "pronoun": current.pronoun,
                "expected": current.expected,
                "given": "",
                "result": "skipped",
            })
            state["skipped"] = state.get("skipped", 0) + 1
            state["streak"] = 0
            state["last"] = {
                "result": "skipped",
                "given": "",
                "verb": current.verb,
                "pronoun": current.pronoun,
                "tense": current.tense,
            }
            state["awaiting_retry"] = False
            state["retry_attempts"] = 0
            state["seq"] += 1
            state["current"] = self._next_question(state).as_state()
            self._check_items_autofinish(state, config)
            return GuessOutcome(state=state, client_view=self.client_view(state))

        # ── retry (untimed free mode) ──────────────────────────────────────
        if action == "retry":
            if not awaiting_retry:
                raise GameError("No hay reintento pendiente.")
            if not guess.strip():
                raise GameError("Escribe la forma correcta para continuar.")
            result = grade(guess, current.expected)
            advance = result in (Match.EXACT, Match.CLOSE)
            retry_attempts = state.get("retry_attempts", 0) + 1
            if not advance and retry_attempts >= _MAX_RETRY_ATTEMPTS:
                advance = True  # forced advance after 2 failed retries
            # Retry does NOT change score/streak/correct/close counts.
            reveal = current.reveal()
            state["last"] = {
                "result": result.value,
                # Marks this feedback as a retype, not a scored answer, so the
                # client doesn't celebrate it as a fresh "Correct!".
                "retry": True,
                "given": guess.strip(),
                "verb": current.verb,
                "pronoun": current.pronoun,
                "tense": current.tense,
                "expected": current.expected,
                "note": reveal["note"],
                "row": reveal["row"],
            }
            if advance:
                state["awaiting_retry"] = False
                state["retry_attempts"] = 0
                state["seq"] += 1
                state["current"] = self._next_question(state).as_state()
                self._check_items_autofinish(state, config)
            else:
                state["awaiting_retry"] = True
                state["retry_attempts"] = retry_attempts
            return GuessOutcome(state=state, client_view=self.client_view(state))

        # ── answer (default) ──────────────────────────────────────────────
        # If client is awaiting_retry and sends action="answer", treat as retry
        # (lenient: avoids race where client didn't see the awaiting_retry flag).
        if awaiting_retry:
            return self.submit(state=state, guess=guess, finish=finish, action="retry")

        result = grade(guess, current.expected)
        is_correct = result == Match.EXACT or (result == Match.CLOSE and not config.strict)

        reveal = current.reveal()
        state["answered"].append({
            "verb": current.verb,
            "tense": current.tense,
            "pronoun": current.pronoun,
            "expected": current.expected,
            "given": guess.strip(),
            "result": result.value,
        })
        if result == Match.CLOSE:
            state["close"] = state.get("close", 0) + 1

        if is_correct:
            state["correct"] += 1
            state["streak"] += 1
            state["best_streak"] = max(state["best_streak"], state["streak"])
        else:
            state["streak"] = 0

        # Feedback on the answer just graded (client flashes this before the
        # next prompt animates in).
        last: dict[str, Any] = {
            "result": result.value,
            "given": guess.strip(),
            "verb": current.verb,
            "pronoun": current.pronoun,
            "tense": current.tense,
            "expected": current.expected,
            "note": reveal["note"],
            "row": reveal["row"],
        }
        state["last"] = last

        # In untimed free mode: after a wrong/close answer, enter retry mode
        # instead of advancing immediately.
        if not timed and not is_correct:
            state["awaiting_retry"] = True
            state["retry_attempts"] = 0
            # Current stays the same.
            return GuessOutcome(state=state, client_view=self.client_view(state))

        # Advance to the next prompt.
        state["awaiting_retry"] = False
        state["retry_attempts"] = 0
        state["seq"] += 1
        state["current"] = self._next_question(state).as_state()
        self._check_items_autofinish(state, config)
        return GuessOutcome(state=state, client_view=self.client_view(state))

    def is_over(self, state: dict[str, Any]) -> bool:
        return state.get("status") == "over"

    # ── result card ───────────────────────────────────────────────────────

    def result_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        config = self._config(state)
        correct = int(state.get("correct", 0))
        answered = state.get("answered", [])
        skipped = int(state.get("skipped", 0) or 0)
        close_count = int(state.get("close", 0) or 0)
        # Total excludes skipped for accuracy denominator.
        total = len([a for a in answered if a.get("result") != "skipped"])
        best_streak = int(state.get("best_streak", 0))

        header = "Conjugación"
        if state.get("puzzle_no") is not None:
            header = f"Conjugación #{state['puzzle_no']}"
        noun = "correcta" if correct == 1 else "correctas"
        summary = f"{header} · {correct} {noun}"
        if config.strict:
            summary += " · estricto"

        # misses = wrong + close in answered order.
        misses = [a for a in answered if a.get("result") in (Match.WRONG.value, Match.CLOSE.value)]

        # review_verbs: distinct verbs from misses, capped at MAX_REVIEW_VERBS.
        seen: set[str] = set()
        review_verbs: list[str] = []
        for a in misses:
            v = a.get("verb", "")
            if v and v not in seen:
                seen.add(v)
                review_verbs.append(v)
                if len(review_verbs) >= d.MAX_REVIEW_VERBS:
                    break

        # Breakdown by tense and pronoun (totals exclude skipped).
        tense_breakdown: dict[str, dict[str, int]] = {}
        pronoun_breakdown: dict[str, dict[str, int]] = {}
        for a in answered:
            if a.get("result") == "skipped":
                continue
            t = a.get("tense", "")
            p = a.get("pronoun", "")
            c = 1 if a.get("result") == Match.EXACT.value or (
                a.get("result") == Match.CLOSE.value and not config.strict
            ) else 0
            if t:
                tb = tense_breakdown.setdefault(t, {"correct": 0, "total": 0})
                tb["correct"] += c
                tb["total"] += 1
            if p:
                pb = pronoun_breakdown.setdefault(p, {"correct": 0, "total": 0})
                pb["correct"] += c
                pb["total"] += 1

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
            "skipped": skipped,
            "close": close_count,
            "strict": config.strict,
            "best_streak": best_streak,
            # Always the N/M shape (a zero-answer run — now reachable via the
            # untimed "Terminar" — reads "0/0", not a bare "0").
            "score": f"{correct}/{total}",
            "grid": self._emoji_grid(answered),
            "summary": summary,
            "misses": misses,
            "review_verbs": review_verbs,
            "breakdown": {
                "tenses": tense_breakdown,
                "pronouns": pronoun_breakdown,
            },
        }

    # ── helpers ───────────────────────────────────────────────────────────

    def client_view(self, state: dict[str, Any]) -> dict[str, Any]:
        """What the client may see. Excludes the pending answer while playing."""
        config = self._config(state)
        answered = state.get("answered", [])
        items = config.items
        remaining: int | None = None
        if items > 0 and not state.get("timed", True):
            # Skips consume an item too: a 10-prompt set is 10 prompts seen,
            # so the client's "answered/items" progress stays monotonic.
            remaining = max(0, items - len(answered))

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
            "answered_count": len(answered),
            "status": state["status"],
            "awaiting_retry": bool(state.get("awaiting_retry", False)),
            "strict": config.strict,
            "items": items,
            "remaining_items": remaining,
            "last": self._client_last(state),
        }
        if not self.is_over(state):
            view["prompt"] = d.Question.from_state(state["current"]).prompt()
        else:
            view["result"] = self.result_payload(state)
        return view

    def _client_last(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Per-answer feedback for the client, with the answer withheld in daily.

        The daily sprint is a fixed, deterministic sequence shared by everyone,
        so revealing each graded form mid-run would let a player harvest the
        whole day's answers (mash junk, read ``expected``, restart, ace it).
        Daily play therefore gets the result flag (exact/close/wrong) but not
        ``expected``, ``note``, or ``row`` — the correct forms are disclosed
        only in the end-of-game recap. Freeplay/practice reveals normally
        (there's nothing to game).
        """
        last = state.get("last")
        if last is None:
            return None
        if state.get("mode") == "daily":
            return {k: v for k, v in last.items() if k not in ("expected", "note", "row")}
        return last

    def _config(self, state: dict[str, Any]) -> d.Config:
        cfg = state.get("config", {})
        if isinstance(cfg, dict):
            return d.Config.from_state(cfg)
        # Fallback for old state lacking full config.
        return d.Config(
            verb_set="high-frequency",
            tenses=list(d.TENSES),
            pronouns=list(d.PRONOUNS),
        )

    def _next_question(self, state: dict[str, Any]) -> d.Question:
        config = self._config(state)
        if state["mode"] == "daily" and state.get("puzzle_no") is not None:
            return _deterministic_question(config, seed=state["puzzle_no"], index=state["seq"])
        current = d.Question.from_state(state["current"])
        return d.pick_question(config, avoid=current)

    @staticmethod
    def _check_items_autofinish(state: dict[str, Any], config: d.Config) -> None:
        """Auto-finish set mode once ``items`` prompts (incl. skips) are done."""
        if (
            config.items > 0
            and not state.get("timed", True)
            and len(state.get("answered", [])) >= config.items
        ):
            state["status"] = "over"

    @staticmethod
    def _deadline(state: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(state["deadline"])

    @staticmethod
    def _emoji_grid(answered: list[dict[str, Any]]) -> str:
        """Compact ✅/🟨/❌/⏭ block for the channel card, 10 per row, capped."""
        marks = {
            Match.EXACT.value: "✅",
            Match.CLOSE.value: "🟨",
            Match.WRONG.value: "❌",
            "skipped": "⏭",
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
        # current must carry tense and pronoun (required by from_state).
        if not isinstance(current.get("tense"), str) or not isinstance(current.get("pronoun"), str):
            raise GameError("Estado de partida inválido.")
        # Reject non-bool awaiting_retry if present.
        ar = state.get("awaiting_retry")
        if ar is not None and not isinstance(ar, bool):
            raise GameError("Estado de partida inválido.")
        # A timed game must carry a parseable deadline; an untimed one has none.
        # Reject the incoherent timed+null-deadline combo up front, otherwise
        # the deadline check in submit() would hit fromisoformat(None) → crash.
        deadline = state.get("deadline")
        if state.get("timed", True) and deadline is None:
            raise GameError("Estado de partida inválido.")
        if deadline is not None:
            try:
                datetime.fromisoformat(deadline)
            except (TypeError, ValueError) as exc:
                raise GameError("Estado de partida inválido.") from exc
