import { useEffect, useMemo, useRef, useState } from "react";
import type { ConjugationView } from "../../api";

interface SprintProps {
  view: ConjugationView;
  busy: boolean;
  error: string | null;
  onAnswer: (guess: string) => void;
  onTimeout: () => void;
  onFinish: () => void;
}

// Live seconds remaining derived from the server-authoritative deadline, ticked
// locally for a smooth countdown. The server is the source of truth for scoring
// (it re-checks the deadline on every submit); this is purely presentational.
// Passing a null deadline (untimed practice) disables the countdown entirely.
function useCountdown(deadlineIso: string | null, onZero: () => void): number {
  const [remaining, setRemaining] = useState(() =>
    deadlineIso ? Math.max(0, Math.ceil((Date.parse(deadlineIso) - Date.now()) / 1000)) : 0,
  );
  const firedRef = useRef(false);
  // Keep the latest onZero without making it an effect dependency. onZero's
  // identity changes on every guess (it closes over the current sealed state);
  // if the effect depended on it, it would re-run and reset firedRef, letting
  // the zero-callback fire repeatedly — which previously produced several
  // phantom "wrong" answers at the buzzer.
  const onZeroRef = useRef(onZero);
  onZeroRef.current = onZero;

  useEffect(() => {
    if (!deadlineIso) return; // untimed: no ticking, no auto-finish
    firedRef.current = false; // reset only for a genuinely new game (new deadline)
    const deadline = Date.parse(deadlineIso);
    const tick = () => {
      const secs = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setRemaining(secs);
      if (secs <= 0 && !firedRef.current) {
        firedRef.current = true; // fire exactly once per game
        onZeroRef.current();
      }
    };
    tick();
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [deadlineIso]);

  return remaining;
}

export default function Sprint({ view, busy, error, onAnswer, onTimeout, onFinish }: SprintProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const remaining = useCountdown(view.deadline, onTimeout);

  const prompt = view.prompt;
  const last = view.last;

  // Re-focus and clear the field whenever a new prompt arrives (keyed on the
  // answered count so it fires once per advance).
  useEffect(() => {
    setValue("");
    inputRef.current?.focus();
  }, [view.answered_count]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const g = value.trim();
    if (!g || busy) return;
    onAnswer(g);
  };

  // Fraction of time remaining, for the depleting timer bar (timed only).
  const frac = useMemo(
    () => (view.duration ? Math.max(0, Math.min(1, remaining / view.duration)) : 1),
    [remaining, view.duration],
  );
  const low = view.timed && remaining <= 10;

  if (!prompt) {
    return (
      <div className="conj">
        <p className="muted">…</p>
      </div>
    );
  }

  return (
    <div className="conj conj-sprint">
      <div className="sprint-top">
        {view.timed ? (
          <div className={`timer${low ? " timer--low" : ""}`}>
            <span className="timer-num">{remaining}</span>
            <div className="timer-track">
              <div className="timer-fill" style={{ transform: `scaleX(${frac})` }} />
            </div>
          </div>
        ) : (
          <button className="finish-btn" onClick={onFinish} disabled={busy}>
            Terminar
          </button>
        )}
        <div className="score-pills">
          <span className="pill pill-score">
            <strong>{view.correct}</strong> ✓
          </span>
          <span className={`pill pill-streak${view.streak >= 3 ? " pill-streak--hot" : ""}`}>
            {view.streak >= 3 ? "🔥" : ""} {view.streak}
          </span>
        </div>
      </div>

      {/* Submit errors (e.g. a network failure) float as a toast so they never
          resize the prompt card. Zero-height anchor = no layout shift. */}
      <div className="toast-anchor">
        {error && (
          <div className="toast" role="status" key={error}>
            {error}
          </div>
        )}
      </div>

      {/* The prompt card. `key` on answered_count forces a remount so the
          enter animation replays for every new prompt (the swap motion). */}
      <div className="prompt-card" key={view.answered_count}>
        <span className="prompt-pronoun">{prompt.pronoun}</span>
        <span className="prompt-verb">{prompt.verb}</span>
        <span className="prompt-meta">
          {prompt.tense_label}
          {prompt.english ? <em className="prompt-gloss"> · {prompt.english}</em> : null}
        </span>
      </div>

      {/* Inline feedback from the previous answer, flashed above the input. */}
      <div className="feedback-slot">
        {last ? (
          <p className={`feedback feedback--${last.result}`} key={view.answered_count}>
            {last.result === "exact" && <span>¡Correcto!</span>}
            {/* `expected` is withheld during the daily sprint, so fall back to
                an answer-free message when it's absent. */}
            {last.result === "close" &&
              (last.expected ? (
                <span>
                  ¡Casi! <strong>{last.expected}</strong> (acentos)
                </span>
              ) : (
                <span>¡Casi! (acentos)</span>
              ))}
            {last.result === "wrong" &&
              (last.expected ? (
                <span>
                  Era <strong>{last.expected}</strong>
                </span>
              ) : (
                <span>Incorrecto</span>
              ))}
          </p>
        ) : null}
      </div>

      <form className="answer-form" onSubmit={submit}>
        <input
          ref={inputRef}
          className="answer-input"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="escribe la conjugación…"
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          enterKeyHint="go"
          disabled={busy}
          aria-label={`Conjuga ${prompt.verb} para ${prompt.pronoun}`}
        />
        <button className="answer-go" type="submit" disabled={busy || !value.trim()}>
          →
        </button>
      </form>
    </div>
  );
}
