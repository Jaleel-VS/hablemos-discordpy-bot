import { useEffect, useRef, useState } from "react";
import type { ClozeView } from "../../api";

interface RoundProps {
  view: ClozeView;
  busy: boolean;
  error: string | null;
  onAnswer: (guess: string) => void;
  onFinish: () => void;
}

// Split a cloze sentence ("El ___ duerme.") around its single blank so the
// blank can be rendered as a styled slot rather than literal underscores.
function splitBlank(cloze: string): [string, string] {
  const idx = cloze.indexOf("___");
  if (idx === -1) return [cloze, ""];
  return [cloze.slice(0, idx), cloze.slice(idx + 3)];
}

export default function Round({ view, busy, error, onAnswer, onFinish }: RoundProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const prompt = view.prompt;
  const last = view.last;
  const isChoice = view.answer_mode === "choice";

  // Clear the field / refocus whenever a new card arrives (keyed on the
  // answered count so it fires once per advance).
  useEffect(() => {
    setValue("");
    if (!isChoice) inputRef.current?.focus();
  }, [view.answered_count, isChoice]);

  const submitType = (e: React.FormEvent) => {
    e.preventDefault();
    const g = value.trim();
    if (!g || busy) return;
    onAnswer(g);
  };

  if (!prompt) {
    return (
      <div className="cloze">
        <p className="muted">…</p>
      </div>
    );
  }

  const [before, after] = splitBlank(prompt.cloze);
  const progress = `${Math.min(view.seq + 1, view.round_size)} / ${view.round_size}`;
  // The daily feeds streaks and only counts when every card is answered, so the
  // backend rejects an early daily finish. Don't offer "Terminar" for the daily
  // (freeplay is practice and may be ended any time).
  const canFinish = view.mode !== "daily";

  return (
    <div className="cloze cloze-round">
      <div className="round-top">
        {canFinish ? (
          <button className="finish-btn" onClick={onFinish} disabled={busy}>
            Terminar
          </button>
        ) : (
          <span className="round-daily-tag">Reto diario</span>
        )}
        <div className="score-pills">
          <span className="pill pill-progress">{progress}</span>
          <span className="pill pill-score">
            <strong>{view.correct}</strong> ✓
          </span>
          <span className={`pill pill-streak${view.streak >= 3 ? " pill-streak--hot" : ""}`}>
            {view.streak >= 3 ? "🔥" : ""} {view.streak}
          </span>
        </div>
      </div>

      {/* Submit errors float as a toast so they never resize the card. */}
      <div className="toast-anchor">
        {error && (
          <div className="toast" role="status" key={error}>
            {error}
          </div>
        )}
      </div>

      {/* The prompt card. `key` on answered_count forces a remount so the
          enter animation replays for every new card. */}
      <div className="prompt-card cloze-card" key={view.answered_count}>
        <p className="cloze-sentence">
          {before}
          <span className="cloze-blank" aria-label="palabra que falta">
            ？
          </span>
          {after}
        </p>
        <p className="cloze-context">{prompt.context}</p>
      </div>

      {/* Inline feedback from the previous answer. */}
      <div className="feedback-slot">
        {last ? (
          <p className={`feedback feedback--${last.result}`} key={view.answered_count}>
            {last.result === "exact" && <span>¡Correcto!</span>}
            {last.result === "close" &&
              (last.answer ? (
                <span>
                  ¡Casi! <strong>{last.answer}</strong> (acentos)
                </span>
              ) : (
                <span>¡Casi! (acentos)</span>
              ))}
            {last.result === "wrong" &&
              (last.answer ? (
                <span>
                  Era <strong>{last.answer}</strong>
                </span>
              ) : (
                <span>Incorrecto</span>
              ))}
          </p>
        ) : null}
      </div>

      {isChoice ? (
        <div className="cloze-options">
          {prompt.options.map((opt) => (
            <button
              key={opt}
              className="cloze-option"
              onClick={() => !busy && onAnswer(opt)}
              disabled={busy}
            >
              {opt}
            </button>
          ))}
        </div>
      ) : (
        <form className="answer-form" onSubmit={submitType}>
          <input
            ref={inputRef}
            className="answer-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="escribe la palabra…"
            autoComplete="off"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            enterKeyHint="go"
            disabled={busy}
            aria-label="Escribe la palabra que falta"
          />
          <button className="answer-go" type="submit" disabled={busy || !value.trim()}>
            →
          </button>
        </form>
      )}
    </div>
  );
}
