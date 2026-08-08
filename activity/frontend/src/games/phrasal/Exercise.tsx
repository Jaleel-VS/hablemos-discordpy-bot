import { useEffect, useRef, useState } from "react";
import type { PhrasalView } from "../../api";

interface ExerciseProps {
  view: PhrasalView;
  busy: boolean;
  error: string | null;
  onAnswer: (guess: string) => void;
  onFinish: () => void;
}

// Split the example ("You can ___ the word.") around its single blank so the
// blank renders as a styled slot rather than literal underscores.
function splitBlank(example: string): [string, string] {
  const idx = example.indexOf("___");
  if (idx === -1) return [example, ""];
  return [example.slice(0, idx), example.slice(idx + 3)];
}

export default function Exercise({ view, busy, error, onAnswer, onFinish }: ExerciseProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const prompt = view.prompt;
  const last = view.last;
  const isChoice = view.answer_mode === "choice";

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
      <div className="phrasal">
        <p className="muted">…</p>
      </div>
    );
  }

  const [before, after] = splitBlank(prompt.example);
  const progress = `${Math.min(view.seq + 1, view.round_size)} / ${view.round_size}`;
  const canFinish = view.mode !== "daily";
  const placeholder = prompt.blank_mode === "particle" ? "partícula…" : "verbo con partícula…";

  return (
    <div className="phrasal phrasal-round">
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
          {view.correct !== null && (
            <span className="pill pill-score">
              <strong>{view.correct}</strong> ✓
            </span>
          )}
          {view.streak !== null && (
            <span className={`pill pill-streak${view.streak >= 3 ? " pill-streak--hot" : ""}`}>
              {view.streak >= 3 ? "🔥" : ""} {view.streak}
            </span>
          )}
        </div>
      </div>

      <div className="toast-anchor">
        {error && (
          <div className="toast" role="status" key={error}>
            {error}
          </div>
        )}
      </div>

      <div className="prompt-card phrasal-card" key={view.answered_count}>
        {/* The meaning hint. All senses are shown (they aren't aligned to the
            example — see the generator), so the learner reads the phrasal
            verb's range; the Spanish gloss (if present) anchors beginners. */}
        <div className="phrasal-meaning">
          {prompt.gloss_es && <span className="phrasal-gloss">{prompt.gloss_es}</span>}
          <ul className="phrasal-defs">
            {prompt.definitions.slice(0, 3).map((def, i) => (
              <li key={i}>{def}</li>
            ))}
          </ul>
        </div>

        <p className="phrasal-sentence">
          {/* In particle mode we show the base verb before the blank so the
              learner knows which verb's particle to supply. */}
          {prompt.base && <span className="phrasal-base-hint">({prompt.base})</span>}
          {before}
          <span className="cloze-blank" aria-label="parte que falta">
            ？
          </span>
          {after}
        </p>
      </div>

      <div className="feedback-slot">
        {last ? (
          <p className={`feedback feedback--${last.result}`} key={view.answered_count}>
            {last.result === "exact" && <span>¡Correcto!</span>}
            {last.result === "close" &&
              (last.answer ? (
                <span>
                  ¡Casi! <strong>{last.answer}</strong>
                </span>
              ) : (
                <span>¡Casi!</span>
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
        ) : view.mode === "daily" && view.answered_count > 0 ? (
          <p className="feedback feedback--daily" key={view.answered_count}>
            <span>Revisa tus respuestas al final</span>
          </p>
        ) : null}
      </div>

      {isChoice && prompt.options ? (
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
            placeholder={placeholder}
            autoComplete="off"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            enterKeyHint="go"
            disabled={busy}
            aria-label="Escribe la parte que falta"
          />
          <button className="answer-go" type="submit" disabled={busy || !value.trim()}>
            →
          </button>
        </form>
      )}
    </div>
  );
}
