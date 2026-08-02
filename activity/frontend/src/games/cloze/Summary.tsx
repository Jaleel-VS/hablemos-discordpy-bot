import type { ClozeResult } from "../../api";

interface SummaryProps {
  result: ClozeResult;
  onReplay: () => void;
}

// A short encouragement keyed to accuracy, so the recap feels responsive.
function verdict(correct: number, total: number): string {
  const acc = total > 0 ? correct / total : 0;
  if (acc >= 0.9) return "¡Impecable!";
  if (acc >= 0.7) return "¡Muy bien!";
  if (acc >= 0.4) return "¡Bien hecho!";
  if (correct >= 1) return "¡Sigue así!";
  return "¡A practicar!";
}

export default function Summary({ result, onReplay }: SummaryProps) {
  const { correct, total, best_streak, misses } = result;
  const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0;

  return (
    <div className="cloze cloze-summary">
      <p className="summary-verdict">{verdict(correct, total)}</p>

      <div className="summary-score">
        <span className="summary-big">
          {correct}/{total}
        </span>
        <span className="summary-big-label">correctas</span>
      </div>

      <div className="summary-stats">
        <span>
          <strong>{accuracy}%</strong> precisión
        </span>
        <span>
          🔥 <strong>{best_streak}</strong> mejor racha
        </span>
      </div>

      {misses.length > 0 && (
        <div className="misses">
          <h2 className="misses-title">Para repasar</h2>
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
              </li>
            ))}
          </ul>
        </div>
      )}

      <button className="cta" onClick={onReplay}>
        Jugar otra
      </button>
    </div>
  );
}
