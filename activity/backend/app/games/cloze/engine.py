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
      "awaiting_retry": false,            # type mode only: true after wrong/close in freeplay
      "retry_attempts": <int>,            # failed retries since awaiting_retry=true
      "awaiting_continue": false,         # choice mode only: true after wrong/close in freeplay
      "status": "playing" | "over",
      "date": "YYYY-MM-DD",
      "last": <null | feedback dict>
    }

The daily round is a fixed, deterministic sequence shared by everyone, so the
per-card feedback withholds the answer in daily mode (anti-harvest) — the client
gets no per-card feedback at all (not even the exact/close/wrong flag), and the
running counters are also withheld. Freeplay reveals normally.

Freeplay miss mechanics:

* **Type mode**: after a wrong/close answer the state transitions to
  ``awaiting_retry=True`` — the same card stays visible and the client must
  retype the correct word (``action="retry"``).  Two failed retries force
  advance.  ``action="skip"`` is allowed when NOT awaiting_retry.
* **Choice mode**: after a wrong/close answer the state transitions to
  ``awaiting_continue=True`` — the client shows the completed sentence + context
  (reveal card) with a Continue button.  The client sends ``action="continue"``
  to advance (no retype, no score change).

Daily mode rejects ``retry``, ``skip``, and ``continue``.
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
_VALID_ACTIONS = {"answer", "skip", "retry", "continue"}
#: After this many failed retries in retry mode, force advance anyway.
_MAX_RETRY_ATTEMPTS = 2
#: Longest stored echo of a guess. Real answers are one word; the request
#: allows 128 chars, and storing that verbatim in every graded row is what let
#: a 10-card round of the heaviest cards outgrow the 8 KB sealed-state cap.
_MAX_GIVEN = 40


def _clip(guess: str) -> str:
    return guess.strip()[:_MAX_GIVEN]


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
            # options.ids: review round — use specified card ids if valid.
            ids_raw = options.get("ids") if isinstance(options, dict) else None
            if isinstance(ids_raw, list) and ids_raw:
                cards_by_ids = d.random_cards_by_ids(
                    ids_raw,
                    target=config.target,
                    count=ROUND_SIZE,
                    config=config,
                )
                cards = cards_by_ids if cards_by_ids else d.random_cards(config, count=ROUND_SIZE)
            else:
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
        if action not in _VALID_ACTIONS:
            raise GameError("Acción no válida.")

        # Daily is a fixed once-per-day sequence that feeds streaks, so a saved
        # token can't be finished on a later day (which would credit a streak
        # for a stale puzzle). Reject a daily submit once the state's date is no
        # longer today — mirrors Wordle's daily date gate. Freeplay has no date.
        if state.get("mode") == "daily" and state.get("date") != _now().date().isoformat():
            raise GameError("El reto diario de ese día ya expiró.")

        # Daily rejects retry/skip/continue (anti-harvest + finish guard).
        if state.get("mode") == "daily" and action in {"retry", "skip", "continue"}:
            raise GameError(f"Acción '{action}' no disponible en el reto diario.")

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
        if not guess.strip() and action not in {"skip", "continue"}:
            raise GameError("Escribe o elige una respuesta.")

        card = self._current_card(state)
        is_daily = state.get("mode") == "daily"
        is_type_mode = state.get("answer_mode") == "type"
        awaiting_retry = bool(state.get("awaiting_retry", False))
        awaiting_continue = bool(state.get("awaiting_continue", False))

        # ── continue (choice mode, freeplay only) ─────────────────────────
        if action == "continue":
            if not awaiting_continue:
                raise GameError("No hay nada que continuar.")
            state["awaiting_continue"] = False
            state["seq"] += 1
            if state["seq"] >= state["round_size"]:
                state["status"] = "over"
            return GuessOutcome(state=state, client_view=self.client_view(state))

        # ── skip (freeplay only, not while a miss is pending) ─────────────
        if action == "skip":
            # A pending miss must be resolved (retype / continue) first; skipping
            # it would record the same card twice and desync answered vs cards.
            if awaiting_retry or awaiting_continue:
                raise GameError("Termina la tarjeta actual antes de saltar.")
            state["answered"].append({
                "id": card.id,
                "answer": card.answer,
                "given": "",
                "result": "skipped",
            })
            state["streak"] = 0
            state["last"] = {"result": "skipped", "given": "", "answer": card.answer}
            state["retry_attempts"] = 0
            state["seq"] += 1
            if state["seq"] >= state["round_size"]:
                state["status"] = "over"
            return GuessOutcome(state=state, client_view=self.client_view(state))

        # ── retry (type mode, freeplay only) ──────────────────────────────
        if action == "retry":
            if not awaiting_retry:
                raise GameError("No hay reintento pendiente.")
            if not guess.strip():
                raise GameError("Escribe la forma correcta para continuar.")
            result = grade(guess, card.answer)
            advance = result in (Match.EXACT, Match.CLOSE)
            retry_attempts = state.get("retry_attempts", 0) + 1
            if not advance and retry_attempts >= _MAX_RETRY_ATTEMPTS:
                advance = True  # force advance after 2 failed retries
            # Retry does NOT change score/streak counts.
            state["last"] = {
                "result": result.value,
                "retry": True,
                "given": _clip(guess),
                "answer": card.answer,
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

        # ── answer (default) ──────────────────────────────────────────────
        # If client is awaiting_retry and sends action="answer", treat as retry
        # (lenient: avoids race where client didn't see the awaiting_retry flag).
        if awaiting_retry:
            return self.submit(state=state, guess=guess, finish=finish, action="retry")
        # If awaiting_continue and sends action="answer", treat as continue.
        if awaiting_continue:
            return self.submit(state=state, guess=guess, finish=finish, action="continue")

        result = grade(guess, card.answer)
        is_correct = result in (Match.EXACT, Match.CLOSE)

        state["answered"].append({
            "id": card.id,
            "answer": card.answer,
            "given": _clip(guess),
            "result": result.value,
        })
        if is_correct:
            state["correct"] += 1
            state["streak"] += 1
            state["best_streak"] = max(state["best_streak"], state["streak"])
        else:
            state["streak"] = 0

        # Feedback on the card just graded (client flashes this before the next
        # card animates in). Answer withheld in daily (see _client_last). The
        # completed sentence/context are derived at view time from the card, not
        # stored: sealed state must stay small whatever cards `options.ids` picks.
        state["last"] = {"result": result.value, "answer": card.answer, "given": _clip(guess)}

        # Freeplay miss mechanics: set awaiting_retry (type) or
        # awaiting_continue (choice) so the client shows a learning reveal.
        if not is_daily and not is_correct:
            if is_type_mode:
                state["awaiting_retry"] = True
                state["retry_attempts"] = 0
                # Do NOT advance seq; same card stays.
                return GuessOutcome(state=state, client_view=self.client_view(state))
            else:
                state["awaiting_continue"] = True
                # Do NOT advance seq; choice reveal card shows, then "continue".
                return GuessOutcome(state=state, client_view=self.client_view(state))

        # Advance; end the round when we've served every card.
        state["seq"] += 1
        if state["seq"] >= state["round_size"]:
            state["status"] = "over"
        state["awaiting_retry"] = False
        state["retry_attempts"] = 0
        state["awaiting_continue"] = False
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

        # Build miss rows: wrong + close. Derive sentence/context from the
        # precomputed card data in state — these are static fields that never
        # change, so deriving them at result time keeps them out of sealed state
        # (sealed state carries only the grading log).
        cards_by_id: dict[str, dict[str, Any]] = {
            c["id"]: c for c in state.get("cards", []) if isinstance(c, dict)
        }
        misses: list[dict[str, Any]] = []
        # review_ids: the ids of wrong+close cards, deduped, capped at 10.
        review_ids: list[str] = []
        seen_review: set[str] = set()
        for a in answered:
            if a["result"] not in (Match.WRONG.value, Match.CLOSE.value):
                continue
            card_raw = cards_by_id.get(a.get("id", ""))
            sentence: str | None = None
            context: str | None = None
            if card_raw:
                answer_word = card_raw.get("answer", a.get("answer", ""))
                cloze_str = card_raw.get("cloze", "")
                sentence = cloze_str.replace("___", answer_word) if cloze_str else None
                context = card_raw.get("context")
            miss_entry: dict[str, Any] = {
                "id": a.get("id", ""),
                "answer": a["answer"],
                "given": a["given"],
                "result": a["result"],
            }
            if sentence is not None:
                miss_entry["sentence"] = sentence
            if context is not None:
                miss_entry["context"] = context
            misses.append(miss_entry)
            card_id = a.get("id", "")
            # Daily recap: a "practise these" round can never contain today's
            # daily cards (data.random_cards_by_ids drops them), so offering
            # them would start an unrelated random round. Only freeplay offers.
            if (
                state.get("mode") != "daily"
                and card_id
                and card_id not in seen_review
                and len(review_ids) < 10
            ):
                seen_review.add(card_id)
                review_ids.append(card_id)

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
            "misses": misses,
            "review_ids": review_ids,
        }

    # ── helpers ───────────────────────────────────────────────────────────

    def client_view(self, state: dict[str, Any]) -> dict[str, Any]:
        """What the client may see. Excludes the pending answer while playing."""
        # During DAILY play every grading signal is withheld (see _client_last):
        # the state round-trips as a replayable sealed token, so exposing the
        # running correct/streak/best_streak counters lets a choice-mode player
        # replay the previous turn's token against each of the four options and
        # watch which one bumps the counters — a replay oracle for the answer.
        # The counters are disclosed only in the end-of-round recap
        # (result_payload), reachable solely by answering every card. Freeplay
        # shows them live (no streak stakes, nothing to game).
        daily_in_progress = state.get("mode") == "daily" and not self.is_over(state)
        view: dict[str, Any] = {
            "game": self.key,
            "mode": state["mode"],
            "answer_mode": state.get("answer_mode", "choice"),
            "target": state.get("target"),
            "difficulty": state.get("difficulty"),
            "puzzle_no": state.get("puzzle_no"),
            "round_size": state.get("round_size", 0),
            "seq": state.get("seq", 0),
            # Progress (seq / answered_count) advances regardless of correctness,
            # so it leaks nothing about the current card and is always shown.
            "answered_count": len(state.get("answered", [])),
            "status": state["status"],
            "awaiting_retry": bool(state.get("awaiting_retry", False)),
            "awaiting_continue": bool(state.get("awaiting_continue", False)),
            "last": self._client_last(state),
        }
        if daily_in_progress:
            # Null (not the running value) so the client can render a neutral
            # placeholder without inferring anything from the number.
            view["correct"] = None
            view["streak"] = None
            view["best_streak"] = None
        else:
            view["correct"] = state.get("correct", 0)
            view["streak"] = state.get("streak", 0)
            view["best_streak"] = state.get("best_streak", 0)
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

        So during daily play we return **no per-card feedback at all**. Note the
        grading counters (correct/streak/best_streak) are ALSO withheld during
        daily play by ``client_view`` for the same reason — otherwise a replayed
        token would reveal the answer by which option bumps the score. The
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
        # The miss reveal needs the completed sentence and its translation; both
        # come from the card at view time (the reveal is for the card still on
        # screen while a miss is pending, i.e. cards[seq]), never from state.
        view = dict(last)
        if state.get("awaiting_retry") or state.get("awaiting_continue"):
            # _validate_state guarantees 0 <= seq < len(cards) while playing.
            card = self._current_card(state)
            view["sentence"] = card.cloze.replace("___", card.answer)
            view["context"] = card.context
        return view

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
        # must be a fully-typed record. These fields flow into result_payload
        # (the recap "misses" list) and reach the client, so a forged entry with
        # a non-str answer/given (e.g. {}), or an out-of-enum result, must be
        # rejected here — otherwise a non-renderable value reaches React.
        answered = state.get("answered")
        if not isinstance(answered, list) or len(answered) > len(cards):
            raise bad()
        valid_results = {m.value for m in Match} | {"skipped"}
        for entry in answered:
            if not isinstance(entry, dict):
                raise bad()
            if entry.get("result") not in valid_results:
                raise bad()
            if not isinstance(entry.get("answer"), str):
                raise bad()
            if not isinstance(entry.get("given"), str):
                raise bad()
        # While playing, the current card must be in range (submit indexes it).
        if state.get("status") == "playing" and seq >= len(cards):
            raise bad()
