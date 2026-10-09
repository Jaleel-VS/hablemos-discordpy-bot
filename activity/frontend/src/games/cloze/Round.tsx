import { useEffect, useRef, useState } from "react";
import type { ClozeView } from "../../api";
import type { Lang } from "../../i18n/lang";
import AccentBar from "../../components/AccentBar";
import { t } from "./i18n";

interface RoundProps {
  view: ClozeView;
  lang: Lang;
  busy: boolean;
  error: string | null;
  onAnswer: (guess: string, action?: "answer" | "retry" | "skip" | "continue") => void;
  onFinish: () => void;
}

// Split a cloze sentence ("El ___ duerme.") around its single blank so the
// blank can be rendered as a styled slot rather than literal underscores.
function splitBlank(cloze: string): [string, string] {
  const idx = cloze.indexOf("___");
  if (idx === -1) return [cloze, ""];
  return [cloze.slice(0, idx), cloze.slice(idx + 3)];
}

export default function Round({ view, lang, busy, error, onAnswer, onFinish }: RoundProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const prompt = view.prompt;
  const last = view.last;
  const isChoice = view.answer_mode === "choice";
  const awaitingRetry = view.awaiting_retry ?? false;
  const awaitingContinue = view.awaiting_continue ?? false;
  const revealing = awaitingRetry || awaitingContinue;

  // Clear the field / refocus whenever a new card arrives (keyed on the
  // answered count so it fires once per advance, not on every re-render).
  useEffect(() => {
    setValue("");
    if (!isChoice) inputRef.current?.focus();
  }, [view.answered_count, isChoice]);

  // Refocus after a retry feedback without clearing value (the player may
  // want to keep some characters, and the error toast should not steal focus).
  useEffect(() => {
    if (awaitingRetry && !isChoice) inputRef.current?.focus();
  }, [awaitingRetry, isChoice]);

  const submitType = (e: React.FormEvent) => {
    e.preventDefault();
    const g = value.trim();
    if (!g || busy) return;
    if (awaitingRetry) {
      onAnswer(g, "retry");
    } else {
      onAnswer(g);
    }
  };

  if (!prompt) {
    return (
      <div className="cloze">
        <p className="muted">…</p>
      </div>
    );
  }

  const [before, after] = splitBlank(prompt.cloze);
  const progress = t(lang, "round.progress", {
    seq: Math.min(view.seq + 1, view.round_size),
    total: view.round_size,
  });
  // The daily feeds streaks and only counts when every card is answered, so the
  // backend rejects an early daily finish. Don't offer "Terminar" for the daily
  // (freeplay is practice and may be ended any time).
  const canFinish = view.mode !== "daily";

  return (
    <div className="cloze cloze-round">
      <div className="round-top">
        {canFinish ? (
          <button className="finish-btn" onClick={onFinish} disabled={busy}>
            {t(lang, "round.finish")}
          </button>
        ) : (
          <span className="round-daily-tag">{t(lang, "round.daily_tag")}</span>
        )}
        <div className="score-pills">
          <span className="pill pill-progress">{progress}</span>
          {/* correct/streak are withheld (null) during daily play so the score
              can't be used as a replay oracle; show them only when present
              (freeplay, or the daily recap). Progress is always safe. */}
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

      {/* Submit errors float as a toast so they never resize the card. */}
      <div className="toast-anchor">
        {error && (
          <div className="toast" role="status" key={error}>
            {error}
          </div>
        )}
      </div>

      {/* The prompt card. `key` on answered_count forces a remount so the
          enter animation replays for every new card. Stays visible during
          awaiting_retry / awaiting_continue (same seq, same card) — and on a
          miss the blank itself fills with the answer, so the correction lands
          exactly where the learner was looking. */}
      <div className="prompt-card cloze-card" key={view.answered_count}>
        <p className="cloze-sentence">
          {before}
          {revealing && last?.answer ? (
            <span className="cloze-blank cloze-blank--revealed">{last.answer}</span>
          ) : (
            <span className="cloze-blank" aria-label="palabra que falta">
              ？
            </span>
          )}
          {after}
        </p>
        <p className="cloze-context">{prompt.context}</p>
      </div>

      {/* Choice mode — awaiting_continue: what they picked, then Continue. */}
      {awaitingContinue && last ? (
        <div className="cloze-miss" key="reveal">
          <p className="cloze-miss-line">
            {t(lang, "miss.you_wrote", { given: last.given || "—" })}
          </p>
          <button
            className="cta cta-continue"
            onClick={() => onAnswer("", "continue")}
            disabled={busy}
          >
            {t(lang, "continue.btn")}
          </button>
        </div>
      ) : awaitingRetry && last ? (
        /* Type mode — awaiting_retry: retype the revealed word to move on. */
        <div className="cloze-miss" key="retry">
          <p className="cloze-miss-line">
            {last.retry
              ? t(lang, "miss.try_again")
              : t(lang, "miss.you_wrote", { given: last.given || "—" })}
          </p>
          <p className="retry-instruction">{t(lang, "retry.instruction")}</p>
        </div>
      ) : (
        /* Normal feedback: inline flash from the previous answer. In the
           daily there is no per-card feedback (backend withholds it) so show
           a subtle note that corrections come at the end instead of an empty
           slot. Freeplay flashes the graded result. */
        <div className="feedback-slot">
          {last ? (
            <p className={`feedback feedback--${last.result}`} key={view.answered_count}>
              {last.retry ? (
                <span>{t(lang, "feedback.retry_ok", { answer: last.answer ?? "" })}</span>
              ) : (
                last.result === "exact" && <span>{t(lang, "feedback.correct")}</span>
              )}
              {!last.retry && last.result === "close" &&
                (last.answer ? (
                  <span>{t(lang, "feedback.close", { answer: last.answer })}</span>
                ) : (
                  <span>{t(lang, "feedback.close.short")}</span>
                ))}
              {!last.retry && last.result === "wrong" &&
                (last.answer ? (
                  <span>{t(lang, "feedback.wrong", { answer: last.answer })}</span>
                ) : (
                  <span>{t(lang, "feedback.wrong.short")}</span>
                ))}
            </p>
          ) : view.mode === "daily" && view.answered_count > 0 ? (
            <p className="feedback feedback--daily" key={view.answered_count}>
              <span>{t(lang, "round.daily_hint")}</span>
            </p>
          ) : null}
        </div>
      )}

      {/* Answer controls. During awaiting_continue the Continue button is
          already shown in the reveal card above; during awaiting_retry the
          type form stays live for the retype. */}
      {!awaitingContinue && (
        isChoice ? (
          <div className="cloze-options">
            {prompt.options?.map((opt) => (
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
          <>
            <form className="answer-form" onSubmit={submitType}>
              <input
                ref={inputRef}
                className="answer-input"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={t(lang, "round.placeholder")}
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
            <AccentBar inputRef={inputRef} value={value} onChange={setValue} />
            {awaitingRetry && (
              <button
                className="skip-btn"
                type="button"
                onClick={() => onAnswer("", "skip")}
                disabled={busy}
              >
                {t(lang, "retry.skip")}
              </button>
            )}
          </>
        )
      )}
    </div>
  );
}
