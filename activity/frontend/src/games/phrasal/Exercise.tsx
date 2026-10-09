import { useEffect, useRef, useState } from "react";
import type { PhrasalView } from "../../api";
import { useLang } from "../../i18n/lang";
import { DEFAULT_LANG, t } from "./i18n";

interface ExerciseProps {
  view: PhrasalView;
  busy: boolean;
  error: string | null;
  onAnswer: (guess: string, finish?: boolean, action?: "answer" | "retry" | "continue") => void;
  onFinish: () => void;
}

// Split the example ("You can ___ the word.") around its single blank so the
// blank renders as a styled slot rather than literal underscores.
function splitBlank(example: string): [string, string] {
  const idx = example.indexOf("___");
  if (idx === -1) return [example, ""];
  return [example.slice(0, idx), example.slice(idx + 3)];
}

// Replace the blank in a filled sentence with a highlighted <strong>.
function FilledSentence({ sentence, answer }: { sentence: string; answer: string }) {
  const idx = sentence.toLowerCase().indexOf(answer.toLowerCase());
  if (idx === -1) return <>{sentence}</>;
  return (
    <>
      {sentence.slice(0, idx)}
      <strong className="reveal-answer">{sentence.slice(idx, idx + answer.length)}</strong>
      {sentence.slice(idx + answer.length)}
    </>
  );
}

export default function Exercise({ view, busy, error, onAnswer, onFinish }: ExerciseProps) {
  const [lang] = useLang(DEFAULT_LANG);
  const [value, setValue] = useState("");
  const [defsOpen, setDefsOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const prompt = view.prompt;
  const last = view.last;
  const isChoice = view.answer_mode === "choice";
  const isDaily = view.mode === "daily";

  // Reset on each new item.
  useEffect(() => {
    setValue("");
    setDefsOpen(false);
    if (!isChoice && !view.awaiting_retry) inputRef.current?.focus();
  }, [view.answered_count, isChoice, view.awaiting_retry]);

  const submitType = (e: React.FormEvent) => {
    e.preventDefault();
    const g = value.trim();
    if (!g || busy) return;
    const action = view.awaiting_retry ? "retry" : "answer";
    onAnswer(g, false, action);
  };

  // ── awaiting_continue: show reveal card, then "Continuar" ────────────────
  if (view.awaiting_continue && last) {
    return (
      <div className="phrasal phrasal-round">
        <div className="round-top">
          <span className="round-daily-tag">{t(lang, "exercise.progress", { done: view.answered_count, total: view.round_size })}</span>
          <div className="score-pills">
            {view.correct !== null && (
              <span className="pill pill-score">
                <strong>{view.correct}</strong> ✓
              </span>
            )}
          </div>
        </div>

        <div className="reveal-card phrasal-reveal" key={view.answered_count}>
          <div className="reveal-verb">{last.verb}</div>
          {last.gloss_es && <p className="reveal-gloss">{last.gloss_es}</p>}
          {last.sentence && last.answer && (
            <p className="reveal-sentence">
              <FilledSentence sentence={last.sentence} answer={last.span ?? last.answer} />
            </p>
          )}
          <p className="reveal-meta reveal-meta--wrong">
            {t(lang, "exercise.feedback.wrong", { answer: last.answer ?? "" })}
          </p>
        </div>

        <div className="answer-actions">
          <button
            className="cta"
            onClick={() => onAnswer("", false, "continue")}
            disabled={busy}
          >
            {t(lang, "exercise.continue")}
          </button>
        </div>
      </div>
    );
  }

  if (!prompt) {
    return (
      <div className="phrasal">
        <p className="muted">{t(lang, "setup.loading")}</p>
      </div>
    );
  }

  const [before, after] = splitBlank(prompt.example);
  const progress = t(lang, "exercise.progress", {
    done: Math.min(view.seq + 1, view.round_size),
    total: view.round_size,
  });
  const placeholder = prompt.blank_mode === "particle"
    ? t(lang, "exercise.placeholder.particle")
    : t(lang, "exercise.placeholder.whole");

  return (
    <div className="phrasal phrasal-round">
      <div className="round-top">
        {view.mode !== "daily" ? (
          <button className="finish-btn" onClick={onFinish} disabled={busy}>
            {t(lang, "exercise.finish")}
          </button>
        ) : (
          <span className="round-daily-tag">{t(lang, "exercise.daily.tag")}</span>
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
        {/* P1: gloss_es is the primary meaning anchor for beginners. */}
        <div className="phrasal-meaning">
          {prompt.gloss_es && (
            <p className="phrasal-gloss-prominent">{prompt.gloss_es}</p>
          )}
          {/* First EN definition shown directly; rest behind disclosure. */}
          {prompt.definitions.length > 0 && (
            <details className="phrasal-def-details" open={defsOpen} onToggle={(e) => setDefsOpen((e.target as HTMLDetailsElement).open)}>
              <summary className="phrasal-def-summary">
                {t(lang, "exercise.def.en_disclosure")}
              </summary>
              <ul className="phrasal-defs">
                {prompt.definitions.slice(0, 1).map((def, i) => (
                  <li key={i}>{def}</li>
                ))}
              </ul>
            </details>
          )}
        </div>

        <p className="phrasal-sentence">
          {/* In particle mode we show the base verb so the learner knows
              which verb's particle to supply. */}
          {prompt.base && !prompt.base_inline && (
            <span className="phrasal-base-hint">({prompt.base})</span>
          )}
          {before}
          {/* On a miss the answer fills the blank where the learner was looking. */}
          {(view.awaiting_retry || view.awaiting_continue) && last?.answer ? (
            <span className="cloze-blank cloze-blank--revealed">{last.answer}</span>
          ) : (
            <span className="cloze-blank" aria-label="parte que falta">？</span>
          )}
          {after}
        </p>
      </div>

      {/* ── awaiting_retry: retype reveal (type mode freeplay miss) ────── */}
      {view.awaiting_retry && last && (
        <div className="reveal-card phrasal-reveal">
          <div className="reveal-verb">{last.verb}</div>
          {last.gloss_es && <p className="reveal-gloss">{last.gloss_es}</p>}
          {last.sentence && last.answer && (
            <p className="reveal-sentence">
              <FilledSentence sentence={last.sentence} answer={last.span ?? last.answer} />
            </p>
          )}
          <p className="reveal-meta">
            {t(lang, "exercise.feedback.retry")}
          </p>
        </div>
      )}

      {/* Feedback slot for correct / close / daily-mode hint */}
      {!view.awaiting_retry && (
        <div className="feedback-slot">
          {last ? (
            <p className={`feedback feedback--${last.result}`} key={view.answered_count}>
              {/* A retype after the reveal didn't score: acknowledge, don't celebrate. */}
              {last.retry && (
                <span>{t(lang, "exercise.feedback.retry_ok", { answer: last.span ?? last.answer ?? "" })}</span>
              )}
              {!last.retry && last.result === "exact" && (
                <span>{t(lang, "exercise.feedback.exact")}</span>
              )}
              {!last.retry && last.result === "close" && (
                <span>{t(lang, "exercise.feedback.close", { answer: last.answer ?? "" })}</span>
              )}
              {!last.retry && last.result === "wrong" && !isDaily && (
                <span>{t(lang, "exercise.feedback.wrong", { answer: last.answer ?? "" })}</span>
              )}
            </p>
          ) : isDaily && view.answered_count > 0 ? (
            <p className="feedback feedback--daily" key={view.answered_count}>
              <span>{t(lang, "exercise.daily.hint")}</span>
            </p>
          ) : null}
        </div>
      )}

      {isChoice && prompt.options ? (
        <div className="cloze-options">
          {prompt.options.map((opt) => (
            <button
              key={opt}
              className="cloze-option"
              onClick={() => !busy && onAnswer(opt, false, "answer")}
              disabled={busy}
            >
              {opt}
            </button>
          ))}
        </div>
      ) : (
        <>
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
              aria-label={t(lang, "exercise.placeholder.particle")}
            />
            <button className="answer-go" type="submit" disabled={busy || !value.trim()}>
              →
            </button>
          </form>
        </>
      )}
    </div>
  );
}
