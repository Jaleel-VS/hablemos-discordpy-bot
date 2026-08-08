"""The phrasal-verb game — an untimed fill-in-the-blank round (GameEngine).

The exercise loop: show an example sentence with the phrasal verb (or just its
particle) blanked, plus the verb's meaning(s); the player supplies the missing
piece — by typing it or picking from four options — gets instant graded
feedback, next item. A round is a fixed number of items (no clock), same shape
as the cloze game.

Two blank modes (``blank_mode`` in start options):
* ``particle`` — blank only the particle ("look ___ the word" → up); the base
  verb is shown. Targets the hard part of phrasal verbs. Default.
* ``whole``    — blank the whole phrasal verb ("I need to ___ that word"); tests
  productive recall. Distractors are other phrasal verbs.

Two answer modes (``answer_mode``): ``choice`` (4-option MC) and ``type`` (free
text, graded with the ñ-safe exact/close/wrong grader reused from conjugation —
here "close" mostly catches capitalization/spacing since phrasal verbs are
unaccented). In ``whole`` type mode any inflected form of the phrase is accepted.

Statelessness / anti-harvest: identical contract to cloze. State round-trips
sealed; daily withholds per-item feedback and the running counters until the
end recap (the daily is a fixed shared sequence and the token is replayable).

The Learn ("Aprender") mode is NOT part of this engine — it's a read-only deck
served by ``GET /api/games/phrasal/deck`` (see main.py). Browsing vocabulary has
no submit/win state, so forcing it through GameEngine would be an abuse of the
contract.
"""
from __future__ import annotations

import secrets
from datetime import UTC, date, datetime
from typing import Any

from app.games.base import GameError, GuessOutcome, Mode
from app.games.conjugation.normalize import Match, grade
from app.games.phrasal import data as d

#: Items per round (daily + default freeplay).
ROUND_SIZE = 10
#: Puzzle #1 epoch for the daily round number (matches the other games).
_EPOCH = date(2026, 1, 1)

_ANSWER_MODES = ("choice", "type")


def _now() -> datetime:
    return datetime.now(UTC)


def _resolve_answer_mode(options: dict[str, Any] | None) -> str:
    if isinstance(options, dict):
        mode = options.get("answer_mode")
        if isinstance(mode, str) and mode in _ANSWER_MODES:
            return mode
    return "choice"


def _grade_against(guess: str, accepted: list[str]) -> Match:
    """Best grade of *guess* over any accepted form (EXACT > CLOSE > WRONG).

    Phrasal verbs accept several correct answers (inflected forms of the whole
    phrase). We grade against each and keep the strongest match so a learner is
    never marked wrong for choosing a valid alternative form.
    """
    best = Match.WRONG
    for form in accepted:
        result = grade(guess, form)
        if result == Match.EXACT:
            return Match.EXACT
        if result == Match.CLOSE:
            best = Match.CLOSE
    return best


class PhrasalEngine:
    """Authoritative untimed phrasal-verb round. Stateless across calls."""

    key = "phrasal"
    display_name = "Phrasal Verbs"

    # ── lifecycle ─────────────────────────────────────────────────────────

    def new_game(
        self, *, mode: Mode, user_id: str, options: dict[str, Any] | None = None,
    ) -> GuessOutcome:
        now = _now()
        today = now.date()
        seed = secrets.token_hex(8)
        answer_mode = _resolve_answer_mode(options)
        blank_mode = d.resolve_blank_mode(options)

        if mode == "daily":
            config = d.default_config()
            puzzle_no = (today - _EPOCH).days + 1
            verbs = d.deterministic_verbs(config, seed=puzzle_no, count=ROUND_SIZE)
        else:
            config = d.resolve_config(options)
            puzzle_no = None
            verbs = d.random_verbs(config, count=ROUND_SIZE)

        if not verbs:
            raise GameError("No hay verbos disponibles.")

        state: dict[str, Any] = {
            "game": self.key,
            "mode": mode,
            "answer_mode": answer_mode,
            "blank_mode": blank_mode,
            "difficulty": config.difficulty,
            "puzzle_no": puzzle_no,
            "round_size": len(verbs),
            "seq": 0,
            "seed": seed,
            "verbs": [v.as_state() for v in verbs],
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

        # Daily is a fixed once-per-day sequence that feeds streaks; a saved
        # token can't be finished on a later day (mirrors cloze/wordle).
        if state.get("mode") == "daily" and state.get("date") != _now().date().isoformat():
            raise GameError("El reto diario de ese día ya expiró.")

        if finish:
            # A daily may only finish by answering every item (else a player
            # banks a completed-daily streak for a partial run). Freeplay may
            # end early (practice, no stakes).
            if state.get("mode") == "daily" and state.get("seq", 0) < state.get("round_size", 0):
                raise GameError("Termina el reto diario para que cuente.")
            state["status"] = "over"
            state["last"] = None
            return GuessOutcome(state=state, client_view=self.client_view(state))

        # Reject an empty guess (grading "" would advance the round without an
        # attempt — see the cloze engine for the full rationale).
        if not guess.strip():
            raise GameError("Escribe o elige una respuesta.")

        verb = self._current_verb(state)
        blank_mode = state.get("blank_mode", "particle")
        accepted = verb.accepted_forms(blank_mode)
        result = _grade_against(guess, accepted)
        is_correct = result in (Match.EXACT, Match.CLOSE)

        # The canonical answer shown in feedback/recap: the particle, or the
        # exact span the blank replaced (the sentence's own inflected form).
        answer = verb.particle if blank_mode == "particle" else verb.example_answer

        state["answered"].append({
            "id": verb.id,
            "verb": verb.verb,
            "answer": answer,
            "given": guess.strip(),
            "result": result.value,
        })
        if is_correct:
            state["correct"] += 1
            state["streak"] += 1
            state["best_streak"] = max(state["best_streak"], state["streak"])
        else:
            state["streak"] = 0

        state["last"] = {
            "result": result.value,
            "answer": answer,
            "verb": verb.verb,
            "given": guess.strip(),
            "definitions": list(verb.definitions),
        }

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

        header = "Phrasal Verbs"
        if state.get("puzzle_no") is not None:
            header = f"Phrasal Verbs #{state['puzzle_no']}"
        summary = f"{header} · {correct}/{total}"

        return {
            "won": True,  # completing the round counts (practice streak)
            "mode": state["mode"],
            "puzzle_no": state.get("puzzle_no"),
            "blank_mode": state.get("blank_mode"),
            "answer_mode": state.get("answer_mode"),
            "guesses_used": correct,  # stats distribution bucket
            "correct": correct,
            "total": total,
            "best_streak": best_streak,
            "score": f"{correct}/{total}",
            "grid": self._emoji_grid(answered),
            "summary": summary,
            # Recap: every WRONG or CLOSE item, so the learner sees the correct
            # answer for anything they didn't nail (crucial in daily, where
            # per-item feedback is withheld during play).
            "misses": [
                a for a in answered
                if a["result"] in (Match.WRONG.value, Match.CLOSE.value)
            ],
        }

    # ── views ───────────────────────────────────────────────────────────────

    def client_view(self, state: dict[str, Any]) -> dict[str, Any]:
        """What the client may see. Excludes the pending answer while playing."""
        daily_in_progress = state.get("mode") == "daily" and not self.is_over(state)
        view: dict[str, Any] = {
            "game": self.key,
            "mode": state["mode"],
            "answer_mode": state.get("answer_mode", "choice"),
            "blank_mode": state.get("blank_mode", "particle"),
            "difficulty": state.get("difficulty"),
            "puzzle_no": state.get("puzzle_no"),
            "round_size": state.get("round_size", 0),
            "seq": state.get("seq", 0),
            "answered_count": len(state.get("answered", [])),
            "status": state["status"],
            "last": self._client_last(state),
        }
        if daily_in_progress:
            view["correct"] = None
            view["streak"] = None
            view["best_streak"] = None
        else:
            view["correct"] = state.get("correct", 0)
            view["streak"] = state.get("streak", 0)
            view["best_streak"] = state.get("best_streak", 0)
        if not self.is_over(state):
            view["prompt"] = self._current_prompt(state)
        else:
            view["result"] = self.result_payload(state)
        return view

    def _client_last(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Per-item feedback, suppressed entirely during daily play.

        Same anti-harvest reasoning as the cloze engine: the daily is a fixed
        shared sequence and the state round-trips as a replayable sealed token,
        so exposing any grading signal mid-run lets a choice-mode player probe
        the answer by replaying the previous turn against each option. Feedback
        (and the running counters, withheld in client_view) is disclosed only in
        the end recap. Freeplay reveals normally.
        """
        if state.get("mode") == "daily" and not self.is_over(state):
            return None
        return state.get("last")

    # ── helpers ───────────────────────────────────────────────────────────

    def _current_prompt(self, state: dict[str, Any]) -> dict[str, Any]:
        verb = self._current_verb(state)
        blank_mode = state.get("blank_mode", "particle")
        answer_mode = state.get("answer_mode", "choice")
        seed = state.get("seed", "")
        options: list[str] | None = None
        if answer_mode == "choice":
            if blank_mode == "particle":
                options = verb.particle_options(seed=seed)
            else:
                # Build whole-verb options from the global pool + shuffle.
                distractors = d.whole_distractors(verb.verb, seed=seed)
                options = d.shuffle(
                    [verb.verb, *distractors], seed=f"{seed}:{verb.id}:whole",
                )
        return verb.prompt(blank_mode=blank_mode, options=options)

    def _current_verb(self, state: dict[str, Any]) -> d.Verb:
        seq = state.get("seq", 0)
        verbs = state.get("verbs", [])
        if not (0 <= seq < len(verbs)):
            raise GameError("Índice de partida inválido.")
        return d.verb_from_dict(verbs[seq])

    def _emoji_grid(self, answered: list[dict[str, Any]]) -> str:
        """Wordle-style result squares (🟩 exact, 🟨 close, ⬛ wrong)."""
        cell = {Match.EXACT.value: "🟩", Match.CLOSE.value: "🟨", Match.WRONG.value: "⬛"}
        return "".join(cell.get(a.get("result", ""), "⬛") for a in answered)

    def _validate_state(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict) or state.get("game") != self.key:
            raise GameError("Estado de partida inválido.")
        if "verbs" not in state or "seq" not in state:
            raise GameError("Estado de partida inválido.")
