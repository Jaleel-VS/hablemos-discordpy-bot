import { useState } from "react";
import type { ConjugationResult } from "../../api";
import { getLang, t, type Lang } from "./i18n";
import PetReaction from "../../pet/PetReaction";

interface SummaryProps {
  result: ConjugationResult;
  onReplay: () => void;
  onReview: (verbs: string[]) => void;
  accessToken: string;
}

function verdictKey(correct: number): string {
  if (correct >= 20) return "summary.verdict.20";
  if (correct >= 12) return "summary.verdict.12";
  if (correct >= 6) return "summary.verdict.6";
  if (correct >= 1) return "summary.verdict.1";
  return "summary.verdict.0";
}

interface BarProps {
  correct: number;
  total: number;
}

function BreakdownBar({ correct, total }: BarProps) {
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0;
  return (
    <div className="breakdown-bar-wrap">
      <div className="breakdown-bar-track">
        <div className="breakdown-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="breakdown-bar-label">
        {correct}/{total} <span className="breakdown-bar-pct">{pct}%</span>
      </span>
    </div>
  );
}

export default function Summary({ result, onReplay, onReview, accessToken }: SummaryProps) {
  const [lang] = useState<Lang>(getLang);
  const { correct, total, best_streak, misses, skipped = 0, close = 0, strict = false, breakdown, review_verbs = [], grid, mode } = result;
  const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0;
  const outcome: "win" | "meh" = total > 0 && correct / total >= 0.8 ? "win" : "meh";

  return (
    <div className="conj conj-summary">
    <div className="conj-inner">
      <div className="pet-reaction-slot">
        <PetReaction accessToken={accessToken} outcome={outcome} />
      </div>
      <p className="summary-verdict">{t(lang, verdictKey(correct))}</p>

      <div className="summary-score">
        <span className="summary-big">{correct}</span>
        <span className="summary-big-label">{t(lang, "summary.correct")}</span>
      </div>

      <div className="summary-stats">
        <span>
          <strong>{accuracy}%</strong> {t(lang, "summary.accuracy")}
        </span>
        <span>
          🔥 <strong>{best_streak}</strong> {t(lang, "summary.best_streak")}
        </span>
        <span>
          <strong>{total}</strong> {t(lang, "summary.attempts")}
        </span>
        {close > 0 && (
          <span>
            <strong>{close}</strong> {t(lang, "summary.close")}
            {strict && <span className="miss-tag">strict</span>}
          </span>
        )}
        {skipped > 0 && (
          <span>
            <strong>{skipped}</strong> {t(lang, "summary.skipped")}
          </span>
        )}
      </div>

      {/* Breakdown section */}
      {breakdown && Object.keys(breakdown.tenses).length > 0 && (
        <div className="breakdown">
          <h2 className="breakdown-title">{t(lang, "summary.breakdown")}</h2>
          {Object.keys(breakdown.tenses).length > 0 && (
            <div className="breakdown-section">
              <h3 className="breakdown-sub">{t(lang, "summary.breakdown.tenses")}</h3>
              {Object.entries(breakdown.tenses).map(([key, stats]) => (
                <div key={key} className="breakdown-row">
                  <span className="breakdown-label">{key}</span>
                  <BreakdownBar correct={stats.correct} total={stats.total} />
                </div>
              ))}
            </div>
          )}
          {Object.keys(breakdown.pronouns).length > 0 && (
            <div className="breakdown-section">
              <h3 className="breakdown-sub">{t(lang, "summary.breakdown.pronouns")}</h3>
              {Object.entries(breakdown.pronouns).map(([key, stats]) => (
                <div key={key} className="breakdown-row">
                  <span className="breakdown-label">{key}</span>
                  <BreakdownBar correct={stats.correct} total={stats.total} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {misses.length > 0 && (
        <div className="misses">
          <h2 className="misses-title">{t(lang, "summary.misses.title")}</h2>
          {/* No 8-cap: scroll via max-height in CSS */}
          <ul className="misses-list misses-list--scroll">
            {misses.map((m, i) => (
              <li className={`miss${m.result === "close" ? " miss--close" : ""}`} key={i}>
                <span className="miss-prompt">
                  {m.pronoun} · {m.verb}
                  <span className="miss-tense"> · {m.tense}</span>
                </span>
                <span className="miss-answer">
                  <span className="miss-given">{m.given || "—"}</span>
                  <span className="miss-arrow">→</span>
                  <span className="miss-correct">{m.expected}</span>
                  {m.result === "close" && <span className="miss-tag">~</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Daily grid share string */}
      {mode === "daily" && grid && (
        <div className="summary-grid">
          <h2 className="misses-title">{t(lang, "summary.grid")}</h2>
          <pre className="summary-grid-text">{grid}</pre>
        </div>
      )}

      <div className="summary-cta-row">
        {review_verbs.length > 0 && (
          <button className="cta" onClick={() => onReview(review_verbs)}>
            {t(lang, "summary.practice_verbs", { n: review_verbs.length })}
          </button>
        )}
        <button className={`cta${review_verbs.length > 0 ? " cta-ghost" : ""}`} onClick={onReplay}>
          {t(lang, "summary.play_again")}
        </button>
      </div>
    </div>
    </div>
  );
}
