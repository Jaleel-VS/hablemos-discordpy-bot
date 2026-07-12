import type { ConjugationResult } from "../../api";

interface SummaryProps {
  result: ConjugationResult;
  onReplay: () => void;
}

// A short encouragement keyed to the score, so the recap feels responsive
// rather than a flat number.
function verdict(correct: number): string {
  if (correct >= 20) return "¡Imparable!";
  if (correct >= 12) return "¡Excelente!";
  if (correct >= 6) return "¡Bien hecho!";
  if (correct >= 1) return "¡Sigue así!";
  return "¡A practicar!";
}

export default function Summary({ result, onReplay }: SummaryProps) {
  const { correct, total, best_streak, misses } = result;
  const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0;

  return (
    <div className="conj conj-summary">
      <p className="summary-verdict">{verdict(correct)}</p>

      <div className="summary-score">
        <span className="summary-big">{correct}</span>
        <span className="summary-big-label">correctas</span>
      </div>

      <div className="summary-stats">
        <span>
          <strong>{accuracy}%</strong> precisión
        </span>
        <span>
          🔥 <strong>{best_streak}</strong> mejor racha
        </span>
        <span>
          <strong>{total}</strong> intentos
        </span>
      </div>

      {misses.length > 0 && (
        <div className="misses">
          <h2 className="misses-title">Para repasar</h2>
          <ul className="misses-list">
            {misses.slice(0, 8).map((m, i) => (
              <li className="miss" key={i}>
                <span className="miss-prompt">
                  {m.pronoun} · {m.verb}
                </span>
                <span className="miss-answer">
                  <span className="miss-given">{m.given || "—"}</span>
                  <span className="miss-arrow">→</span>
                  <span className="miss-correct">{m.expected}</span>
                </span>
              </li>
            ))}
          </ul>
          {misses.length > 8 && (
            <p className="muted misses-more">y {misses.length - 8} más</p>
          )}
        </div>
      )}

      <button className="cta" onClick={onReplay}>
        Jugar otra
      </button>
    </div>
  );
}
