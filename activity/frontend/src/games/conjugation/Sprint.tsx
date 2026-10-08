import { useEffect, useMemo, useRef, useState } from "react";
import type { ConjugationView } from "../../api";
import AccentBar from "./AccentBar";
import { getLang, t, tenseLabel, type Lang } from "./i18n";

interface SprintProps {
  view: ConjugationView;
  busy: boolean;
  error: string | null;
  onAnswer: (guess: string, finish?: boolean, action?: "answer" | "skip" | "retry") => void;
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
    if (!deadlineIso) return;
    firedRef.current = false;
    const tick = () => {
      const s = Math.max(0, Math.ceil((Date.parse(deadlineIso) - Date.now()) / 1000));
      setRemaining(s);
      if (s === 0 && !firedRef.current) {
        firedRef.current = true;
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
  const [lang] = useState<Lang>(getLang);
  const remaining = useCountdown(view.deadline, onTimeout);

  const prompt = view.prompt;
  const last = view.last;
  const isRetry = view.awaiting_retry;

  // Re-focus and clear the field whenever a new prompt arrives (keyed on the
  // answered count so it fires once per advance). Don't clear during retry —
  // the player needs to see what they typed.
  useEffect(() => {
    if (!isRetry) {
      setValue("");
    }
    inputRef.current?.focus();
  }, [view.answered_count, isRetry]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const g = value.trim();
    if (!g || busy) return;
    const action = isRetry ? "retry" : "answer";
    onAnswer(g, false, action);
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

  // ── feedback line (timed modes or exact results) ──────────────────────────
  const feedbackLine = last && !isRetry ? (() => {
    const r = last.result;
    // A retype after the reveal: acknowledge, don't celebrate (it didn't score).
    if (last.retry) {
      return (
        <span>
          {r === "wrong"
            ? t(lang, "feedback.retry.moveon", { expected: last.expected ?? "" })
            : t(lang, "feedback.retry.ok", { expected: last.expected ?? "" })}
        </span>
      );
    }
    if (r === "exact") return <span>{t(lang, "feedback.exact")}</span>;
    if (r === "skipped") return <span>{t(lang, "feedback.skipped")}</span>;
    if (r === "close") {
      if (view.strict) {
        return (
          <span>
            {last.expected
              ? t(lang, "feedback.close.strict.expected", { expected: last.expected })
              : t(lang, "feedback.close.strict")}
          </span>
        );
      }
      return (
        <span>
          {last.expected
            ? t(lang, "feedback.close.expected", { expected: last.expected })
            : t(lang, "feedback.close")}
          {last.note ? <em className="feedback-note"> · {last.note}</em> : null}
        </span>
      );
    }
    // wrong
    return (
      <span>
        {last.expected
          ? t(lang, "feedback.wrong.expected", { expected: last.expected })
          : t(lang, "feedback.wrong")}
        {last.note ? <em className="feedback-note"> · {last.note}</em> : null}
      </span>
    );
  })() : null;

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
        ) : view.items > 0 ? (
          /* Set-mode: show answered/total instead of timer */
          <span className="pill pill-progress">
            {t(lang, "sprint.progress", {
              done: view.answered_count,
              total: view.items,
            })}
          </span>
        ) : (
          <button className="finish-btn" onClick={onFinish} disabled={busy}>
            {t(lang, "sprint.finish")}
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

      {/* Submit errors float as a toast so they never resize the prompt card. */}
      <div className="toast-anchor">
        {error && (
          <div className="toast" role="status" key={error}>
            {error}
          </div>
        )}
      </div>

      {/* The prompt card. `key` on answered_count forces a remount so the
          enter animation replays for every new prompt (the swap motion).
          During retry we keep the same answered_count so the card stays. */}
      <div className="prompt-card" key={isRetry ? "retry" : view.answered_count}>
        <div className="prompt-pronoun-block">
          <span className="prompt-pronoun">{prompt.pronoun}</span>
          {lang === "en" && prompt.pronoun_english && (
            <span className="prompt-pronoun-en">{prompt.pronoun_english}</span>
          )}
        </div>
        <span className="prompt-verb">{prompt.verb}</span>
        <span className="prompt-meta">
          {tenseLabel(lang, { label: prompt.tense_label, english: prompt.tense_english })}
          {prompt.english ? <em className="prompt-gloss"> · {prompt.english}</em> : null}
        </span>
      </div>

      {/* Retry reveal card replaces normal feedback in untimed free mode */}
      {isRetry && last ? (
        <div className="reveal-card">
          <p className="reveal-expected">{last.expected}</p>
          {last.note && <p className="reveal-note">{last.note}</p>}
          {last.row && (
            <table className="row-table">
              <tbody>
                {Object.entries(last.row).map(([slot, form]) => (
                  <tr
                    key={slot}
                    className={slot === last.pronoun ? "row-table__row--active" : undefined}
                  >
                    <td className="row-table__pronoun">{slot}</td>
                    <td className="row-table__form">{form}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="reveal-instruction">{t(lang, "retry.instruction")}</p>
        </div>
      ) : (
        /* Normal inline feedback slot */
        <div className="feedback-slot">
          {feedbackLine ? (
            <p className={`feedback feedback--${last!.result}`} key={view.answered_count}>
              {feedbackLine}
            </p>
          ) : null}
        </div>
      )}

      <AccentBar inputRef={inputRef} value={value} onChange={setValue} />

      <form className="answer-form" onSubmit={submit}>
        <input
          ref={inputRef}
          className="answer-input"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={t(lang, "sprint.placeholder")}
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          enterKeyHint="go"
          disabled={busy}
          aria-label={`${isRetry ? t(lang, "retry.instruction") : "Conjugate"} ${prompt.verb} ${prompt.pronoun}`}
        />
        <button className="answer-go" type="submit" disabled={busy || !value.trim()}>
          →
        </button>
      </form>

      {/* Skip button — hidden while awaiting retry */}
      {!isRetry && (
        <button
          className="skip-btn"
          type="button"
          onClick={() => onAnswer("", false, "skip")}
          disabled={busy}
        >
          {t(lang, "sprint.skip")}
        </button>
      )}

      {/* Format hint under input on first prompt */}
      {view.answered_count === 0 && (
        <p className="sprint-format-hint muted">{t(lang, "sprint.format.hint")}</p>
      )}
    </div>
  );
}
