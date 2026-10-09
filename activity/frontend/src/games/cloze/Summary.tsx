import type { ClozeResult } from "../../api";
import type { Lang } from "../../i18n/lang";
import PetReaction from "../../pet/PetReaction";
import { t } from "./i18n";

interface SummaryProps {
  result: ClozeResult;
  lang: Lang;
  onReplay: () => void;
  onPractiseMisses: (ids: string[]) => void;
  accessToken: string;
}

function verdictKey(correct: number, total: number): string {
  const acc = total > 0 ? correct / total : 0;
  if (acc >= 0.9) return "summary.verdict.90";
  if (acc >= 0.7) return "summary.verdict.70";
  if (acc >= 0.4) return "summary.verdict.40";
  if (correct >= 1) return "summary.verdict.1";
  return "summary.verdict.0";
}

export default function Summary({ result, lang, onReplay, onPractiseMisses, accessToken }: SummaryProps) {
  const { correct, total, best_streak, misses, review_ids = [] } = result;
  const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0;
  const outcome: "win" | "meh" = total > 0 && correct / total >= 0.8 ? "win" : "meh";

  return (
    <div className="cloze cloze-summary">
      <div className="pet-reaction-slot">
        <PetReaction accessToken={accessToken} outcome={outcome} />
      </div>
      <p className="summary-verdict">{t(lang, verdictKey(correct, total))}</p>

      <div className="summary-score">
        <span className="summary-big">
          {correct}/{total}
        </span>
        <span className="summary-big-label">{t(lang, "summary.correct")}</span>
      </div>

      <div className="summary-stats">
        <span>
          <strong>{accuracy}%</strong> {t(lang, "summary.accuracy")}
        </span>
        <span>
          🔥 <strong>{best_streak}</strong> {t(lang, "summary.best_streak")}
        </span>
      </div>

      {misses.length > 0 && (
        <div className="misses">
          <h2 className="misses-title">{t(lang, "summary.review_title")}</h2>
          <ul className="misses-list">
            {misses.map((m, i) => (
              <li className={`miss miss--${m.result}`} key={i}>
                <span className="miss-answer">
                  <span className="miss-given">{m.given || "—"}</span>
                  <span className="miss-arrow">→</span>
                  <span className="miss-correct">{m.answer}</span>
                  {/* A CLOSE answer counted as correct but had an accent error;
                      tag it so the learner knows they were only off by accents,
                      not fully wrong. */}
                  {m.result === "close" && (
                    <span className="miss-tag">acentos</span>
                  )}
                </span>
                {/* Completed sentence + context (freeplay and daily recap) */}
                {m.sentence && (
                  <span className="miss-sentence">{m.sentence}</span>
                )}
                {m.context && (
                  <span className="miss-context">{m.context}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Pinned to the bottom of the scroll area (see phrasal Summary). */}
      <div className="summary-actions">
        {review_ids.length > 0 && (
          <button className="cta" onClick={() => onPractiseMisses(review_ids)}>
            {t(lang, "summary.practice_these", { n: review_ids.length })}
          </button>
        )}
        <button className={`cta${review_ids.length > 0 ? " cta-ghost" : ""}`} onClick={onReplay}>
          {t(lang, "summary.play_again")}
        </button>
      </div>
    </div>
  );
}
