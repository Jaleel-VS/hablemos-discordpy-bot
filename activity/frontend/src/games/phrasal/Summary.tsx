import type { PhrasalResult } from "../../api";
import PetReaction from "../../pet/PetReaction";
import { useLang } from "../../i18n/lang";
import { DEFAULT_LANG, t } from "./i18n";

interface SummaryProps {
  result: PhrasalResult;
  onReplay: () => void;
  onPracticeIds: (ids: string[]) => void;
  accessToken: string;
}

// Replace blank in filled sentence with highlighted answer span.
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

export default function Summary({ result, onReplay, onPracticeIds, accessToken }: SummaryProps) {
  const [lang] = useLang(DEFAULT_LANG);
  const { correct, total, best_streak, misses, review_ids } = result;
  const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0;
  const outcome: "win" | "meh" = total > 0 && correct / total >= 0.8 ? "win" : "meh";

  const verdictKey =
    accuracy >= 90 ? "summary.verdict.90"
    : accuracy >= 70 ? "summary.verdict.70"
    : accuracy >= 40 ? "summary.verdict.40"
    : correct >= 1  ? "summary.verdict.1"
    : "summary.verdict.0";

  return (
    <div className="phrasal phrasal-summary">
      <div className="pet-reaction-slot">
        <PetReaction accessToken={accessToken} outcome={outcome} />
      </div>
      <p className="summary-verdict">{t(lang, verdictKey)}</p>

      <div className="summary-score">
        <span className="summary-big">{correct}/{total}</span>
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
          <h2 className="misses-title">{t(lang, "summary.misses.title")}</h2>
          <ul className="misses-list">
            {misses.map((m, i) => (
              <li className={`reveal-card phrasal-miss-card miss--${m.result}`} key={i}>
                <div className="reveal-verb">{m.verb}</div>
                {m.gloss_es && (
                  <p className="reveal-gloss">{m.gloss_es}</p>
                )}
                {m.sentence && m.answer && (
                  <p className="reveal-sentence">
                    <FilledSentence sentence={m.sentence} answer={m.span ?? m.answer} />
                  </p>
                )}
                <p className="miss-given-row">
                  <span className="miss-given">{m.given || "—"}</span>
                  <span className="miss-arrow">→</span>
                  <span className="miss-correct">{m.answer}</span>
                  {m.result === "close" && <span className="miss-tag">casi</span>}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Pinned to the bottom of the scroll area: with several miss cards the
          review button would otherwise sit far below the fold. */}
      <div className="summary-actions">
        {review_ids.length > 0 && (
          <button className="cta" onClick={() => onPracticeIds(review_ids)}>
            {t(lang, "summary.practice_n", { n: review_ids.length })}
          </button>
        )}
        <button className={`cta${review_ids.length > 0 ? " cta-ghost" : ""}`} onClick={onReplay}>
          {t(lang, "summary.play_again")}
        </button>
      </div>
    </div>
  );
}
