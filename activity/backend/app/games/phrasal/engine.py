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

Sealed state shape (slim: verb ids only, rebuilt on every submit)::

    {
      "game":            "phrasal",
      "mode":            "daily" | "free",
      "answer_mode":     "choice" | "type",
      "blank_mode":      "particle" | "whole",
      "difficulty":      <str | None>,
      "puzzle_no":       <int | null>,
      "round_size":      <int>,
      "seq":             <int>,
      "seed":            <str>,
      "verb_ids":        [<str>, ...],          # ids only; verbs rebuilt at submit
      "answered":        [{id, verb, answer, given, result}, ...],
      "correct":         <int>,
      "streak":          <int>,
      "best_streak":     <int>,
      "awaiting_retry":  <bool>,                # type mode: retype required
      "retry_attempts":  <int>,                 # failed retries since entering mode
      "awaiting_continue": <bool>,              # choice mode: must confirm after miss
      "status":          "playing" | "over",
      "last":            {result, answer, verb, given, gloss_es?, sentence?} | null,
      "date":            "YYYY-MM-DD"
    }

Statelessness / anti-harvest: identical contract to cloze. State round-trips
sealed; daily withholds per-item feedback and the running counters until the
end recap.

Security invariants (all modes):
- Verb ids only in sealed state; verb objects are rebuilt from the in-memory
  deck by id on every submit.  Unknown ids → GameError (hostile state).
- Prompt view never includes the verb id (no harvesting by id guessing).
- Daily: skip/retry/continue are rejected (only ``answer`` and ``finish`` are
  valid); per-answer reveal is withheld; reveal only in the end recap.
- ``review_ids`` in the result payload: deduplicated, capped at 10, restricted
  to ids that exist in the deck and are NOT in today's deterministic daily set
  so the caller cannot pass them back to ``options.ids`` and replay daily
  answers via freeplay.

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
#: After this many failed retries in type mode, advance anyway.
_MAX_RETRY_ATTEMPTS = 2

_ANSWER_MODES = ("choice", "type")
#: Phrasal has no skip: every item is answered (or finished early in freeplay).
_VALID_ACTIONS = {"answer", "retry", "continue"}


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


def _today_daily_ids() -> set[str]:
    """Ids that appear in today's deterministic daily round.

    Used by ``review_ids`` validation so a caller cannot pass a daily id back
    via ``options.ids`` and replay the answer via a freeplay round.
    """
    today = _now().date()
    seed = (today - _EPOCH).days + 1
    # No exception guard: if the daily picker fails, /start must fail loudly
    # rather than silently drop the exclusion and leak today's daily answers.
    return {v.id for v in d.deterministic_verbs(d.default_config(), seed=seed, count=ROUND_SIZE)}


def _resolve_ids_option(options: dict[str, Any] | None) -> list[str] | None:
    """Validate and return the ``ids`` override from freeplay options.

    Rules (security invariants):
    - Must be a non-empty list of strings.
    - Deduplicated, capped at 10.
    - Every id must exist in the in-memory deck.
    - Any id that is in today's deterministic daily set is silently dropped.
    - If nothing valid remains after drops, returns ``None`` (fall back to
      random round).
    """
    if not isinstance(options, dict):
        return None
    raw = options.get("ids")
    if not isinstance(raw, list) or not raw:
        return None
    # Deduplicate, preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for item in raw:
        if isinstance(item, str) and item not in seen:
            seen.add(item)
            deduped.append(item)
    # Cap.
    capped = deduped[:10]
    # Validate against in-memory deck.
    deck_ids = {v["id"] for v in d._ALL}
    daily_ids = _today_daily_ids()
    valid = [vid for vid in capped if vid in deck_ids and vid not in daily_ids]
    return valid if valid else None


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
            # IDs override: attempt a fixed verb set (review mode).
            ids = _resolve_ids_option(options)
            if ids is not None:
                verbs = d.verbs_by_ids(ids)
            else:
                verbs = d.random_verbs(config, count=ROUND_SIZE)

        if not verbs:
            raise GameError("No hay verbos disponibles.")

        state: dict[str, Any] = {
            "game": self.key,
            "mode": mode,
            "answer_mode": answer_mode,
            "blank_mode": blank_mode,
            "difficulty": config.difficulty if mode != "daily" else None,
            "puzzle_no": puzzle_no,
            "round_size": len(verbs),
            "seq": 0,
            "seed": seed,
            # Slim: only ids; rebuilt from the in-memory deck on every submit.
            "verb_ids": [v.id for v in verbs],
            "answered": [],
            "correct": 0,
            "streak": 0,
            "best_streak": 0,
            "awaiting_retry": False,
            "retry_attempts": 0,
            "awaiting_continue": False,
            "status": "playing",
            "date": today.isoformat(),
            "last": None,
        }
        return GuessOutcome(state=state, client_view=self.client_view(state))

    def submit(
        self, *, state: dict[str, Any], guess: str, finish: bool = False, action: str = "answer",
    ) -> GuessOutcome:
        self._validate_state(state)
        if state["status"] != "playing":
            raise GameError("Esta partida ya terminó.")

        is_daily = state.get("mode") == "daily"

        # Daily is a fixed once-per-day sequence that feeds streaks; a saved
        # token can't be finished on a later day (mirrors cloze/wordle).
        if is_daily and state.get("date") != _now().date().isoformat():
            raise GameError("El reto diario de ese día ya expiró.")

        # Daily mode: only answer and finish are valid.
        if is_daily and action in ("skip", "retry", "continue"):
            raise GameError("Acción no disponible en el reto diario.")

        if finish:
            # A daily may only finish by answering every item.
            if is_daily and state.get("seq", 0) < state.get("round_size", 0):
                raise GameError("Termina el reto diario para que cuente.")
            state["status"] = "over"
            state["last"] = None
            return GuessOutcome(state=state, client_view=self.client_view(state))

        if action not in _VALID_ACTIONS:
            raise GameError(f"Acción inválida: {action!r}.")

        # ── awaiting_continue (choice mode after a miss, freeplay) ────────
        if state.get("awaiting_continue"):
            if action == "continue":
                state["awaiting_continue"] = False
                state["seq"] += 1
                if state["seq"] >= state["round_size"]:
                    state["status"] = "over"
                return GuessOutcome(state=state, client_view=self.client_view(state))
            # Any action other than "continue" while awaiting is rejected so
            # the client can't skip the reveal.
            raise GameError("Confirma antes de continuar.")

        # Reject an empty guess.
        if not guess.strip():
            raise GameError("Escribe o elige una respuesta.")

        verb = self._current_verb(state)
        blank_mode = state.get("blank_mode", "particle")
        answer_mode = state.get("answer_mode", "choice")
        accepted = verb.accepted_forms(blank_mode)
        result = _grade_against(guess, accepted)
        is_correct = result in (Match.EXACT, Match.CLOSE)

        # The canonical answer shown in feedback/recap.
        answer = verb.particle if blank_mode == "particle" else verb.example_answer

        # ── retry (type mode, freeplay, retype after a miss) ─────────────
        if state.get("awaiting_retry"):
            if action not in ("retry", "answer"):
                raise GameError("Reescribe la respuesta para continuar.")
            retry_result = _grade_against(guess, accepted)
            retry_correct = retry_result in (Match.EXACT, Match.CLOSE)
            retry_attempts = state.get("retry_attempts", 0) + 1
            advance = retry_correct or retry_attempts >= _MAX_RETRY_ATTEMPTS
            # Retries do NOT change score/streak/correct counts.
            state["last"] = {
                "result": retry_result.value,
                "retry": True,
                "given": guess.strip(),
                "verb": verb.verb,
                "answer": answer,
                "gloss_es": verb.gloss_es,
                "sentence": _filled_sentence(verb),
                "span": verb.example_answer,
            }
            if advance:
                state["awaiting_retry"] = False
                state["retry_attempts"] = 0
                state["seq"] += 1
                if state["seq"] >= state["round_size"]:
                    state["status"] = "over"
            else:
                state["awaiting_retry"] = True
                state["retry_attempts"] = retry_attempts
            return GuessOutcome(state=state, client_view=self.client_view(state))

        # ── normal answer ─────────────────────────────────────────────────
        state["answered"].append({
            "id": verb.id,
            "verb": verb.verb,
            "answer": answer,
            "given": guess.strip(),
            "result": result.value,
            "gloss_es": verb.gloss_es,
            "sentence": _filled_sentence(verb),
            "span": verb.example_answer,
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
            "gloss_es": verb.gloss_es,
            "sentence": _filled_sentence(verb),
            "span": verb.example_answer,
            "definitions": list(verb.definitions),
        }

        # Freeplay miss handling:
        # - type mode → awaiting_retry (retype; 2 failed retries then advance)
        # - choice mode → awaiting_continue (must confirm before next item)
        if not is_daily and not is_correct:
            if answer_mode == "type":
                state["awaiting_retry"] = True
                state["retry_attempts"] = 0
                return GuessOutcome(state=state, client_view=self.client_view(state))
            else:
                state["awaiting_continue"] = True
                return GuessOutcome(state=state, client_view=self.client_view(state))

        # Correct answer, or daily (advance immediately regardless).
        state["awaiting_retry"] = False
        state["retry_attempts"] = 0
        state["awaiting_continue"] = False
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

        misses = [a for a in answered if a["result"] in (Match.WRONG.value, Match.CLOSE.value)]

        # review_ids: wrong+close ids, validated, capped 10, today's daily ids dropped.
        daily_ids = _today_daily_ids()
        deck_ids = {v["id"] for v in d._ALL}
        seen_ids: set[str] = set()
        review_ids: list[str] = []
        for m in misses:
            vid = m.get("id", "")
            if vid and vid not in seen_ids and vid in deck_ids and vid not in daily_ids:
                seen_ids.add(vid)
                review_ids.append(vid)
                if len(review_ids) >= 10:
                    break

        return {
            "won": True,
            "mode": state["mode"],
            "puzzle_no": state.get("puzzle_no"),
            "blank_mode": state.get("blank_mode"),
            "answer_mode": state.get("answer_mode"),
            "guesses_used": correct,
            "correct": correct,
            "total": total,
            "best_streak": best_streak,
            "score": f"{correct}/{total}",
            "grid": self._emoji_grid(answered),
            "summary": summary,
            "misses": misses,
            "review_ids": review_ids,
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
            "awaiting_retry": bool(state.get("awaiting_retry")),
            "awaiting_continue": bool(state.get("awaiting_continue")),
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
                distractors = d.whole_distractors(verb.verb, seed=seed)
                options = d.shuffle(
                    [verb.verb, *distractors], seed=f"{seed}:{verb.id}:whole",
                )
        return verb.prompt(blank_mode=blank_mode, options=options)

    def _current_verb(self, state: dict[str, Any]) -> d.Verb:
        seq = state.get("seq", 0)
        verb_ids = state.get("verb_ids", [])
        if not (0 <= seq < len(verb_ids)):
            raise GameError("Índice de partida inválido.")
        verb_id = verb_ids[seq]
        # Type before lookup: an unhashable id in a forged state would raise
        # TypeError (500) in the dict lookup instead of a clean GameError.
        verb = d.verb_by_id(verb_id) if isinstance(verb_id, str) else None
        if verb is None:
            raise GameError("Estado de partida inválido.")
        return verb

    def _emoji_grid(self, answered: list[dict[str, Any]]) -> str:
        """Wordle-style result squares (🟩 exact, 🟨 close, ⬛ wrong)."""
        cell = {Match.EXACT.value: "🟩", Match.CLOSE.value: "🟨", Match.WRONG.value: "⬛"}
        return "".join(cell.get(a.get("result", ""), "⬛") for a in answered)

    def _validate_state(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict) or state.get("game") != self.key:
            raise GameError("Estado de partida inválido.")
        if "verb_ids" not in state or "seq" not in state:
            raise GameError("Estado de partida inválido.")


def _filled_sentence(verb: d.Verb) -> str:
    """The example sentence read correctly, for the miss reveal.

    The example's blank always stands for the whole inflected span
    (``example_answer``: "signing over"), even in particle mode where the
    learner only types "over" — so filling it with the particle alone would
    show broken English ("nervous about over the farm"). Always fill with the
    full span; the UI highlights the part that was asked.
    """
    return verb.example.replace("___", verb.example_answer, 1)
