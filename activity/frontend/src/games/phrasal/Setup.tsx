import { useState } from "react";
import type { StartOptions } from "../../api";

interface SetupProps {
  onStart: (mode: "daily" | "free", options?: StartOptions) => void;
  onLearn: () => void;
  busy: boolean;
  error: string | null;
}

// UI is Spanish (the community is Spanish natives learning English); the
// CONTENT (the phrasal verbs) is English.
const DIFFICULTIES: { key: string; label: string }[] = [
  { key: "beginner", label: "Principiante" },
  { key: "intermediate", label: "Intermedio" },
  { key: "advanced", label: "Avanzado" },
];

const BLANK_MODES: { key: "particle" | "whole"; label: string; sub: string }[] = [
  { key: "particle", label: "Partícula", sub: "look ___ → up" },
  { key: "whole", label: "Verbo completo", sub: "I need to ___ → look up" },
];

const ANSWER_MODES: { key: "choice" | "type"; label: string }[] = [
  { key: "choice", label: "Opción múltiple" },
  { key: "type", label: "Escribir" },
];

export default function Setup({ onStart, onLearn, busy, error }: SetupProps) {
  const [difficulty, setDifficulty] = useState<string | null>(null);
  const [blankMode, setBlankMode] = useState<"particle" | "whole">("particle");
  const [answerMode, setAnswerMode] = useState<"choice" | "type">("choice");

  const options: StartOptions = {
    blank_mode: blankMode,
    answer_mode: answerMode,
    ...(difficulty ? { difficulty } : {}),
  };

  return (
    <div className="phrasal phrasal-setup">
      <div className="setup-lede">
        <h1 className="setup-title">Phrasal Verbs</h1>
        <p className="muted">
          Los verbos con partícula del inglés. Aprende o practica.
        </p>
      </div>

      {/* The two top-level branches: browse to learn, or play the daily. */}
      <button className="cta cta-learn" onClick={onLearn} disabled={busy}>
        <span className="cta-daily-main">Aprender 📖</span>
        <span className="cta-daily-sub">Explora los verbos con su significado y ejemplo</span>
      </button>

      <button
        className="cta cta-daily"
        onClick={() => onStart("daily", { blank_mode: blankMode, answer_mode: answerMode })}
        disabled={busy}
      >
        <span className="cta-daily-main">Reto diario</span>
        <span className="cta-daily-sub">Mismos verbos para todos · cuenta para tu racha</span>
      </button>

      <div className="setup-divider">
        <span>o practica libre</span>
      </div>

      <fieldset className="setup-group">
        <legend>Qué completar</legend>
        <div className="chips">
          {BLANK_MODES.map((m) => (
            <button
              key={m.key}
              className={`chip${blankMode === m.key ? " chip--on" : ""}`}
              onClick={() => setBlankMode(m.key)}
              title={m.sub}
            >
              {m.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="setup-group">
        <legend>Nivel</legend>
        <div className="chips">
          <button
            className={`chip${difficulty === null ? " chip--on" : ""}`}
            onClick={() => setDifficulty(null)}
          >
            Mixto
          </button>
          {DIFFICULTIES.map((dfc) => (
            <button
              key={dfc.key}
              className={`chip${difficulty === dfc.key ? " chip--on" : ""}`}
              onClick={() => setDifficulty(dfc.key)}
            >
              {dfc.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="setup-group">
        <legend>Respuesta</legend>
        <div className="chips">
          {ANSWER_MODES.map((m) => (
            <button
              key={m.key}
              className={`chip${answerMode === m.key ? " chip--on" : ""}`}
              onClick={() => setAnswerMode(m.key)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="setup-error-slot">{error && <p className="error">{error}</p>}</div>

      <div className="setup-actions">
        <button className="cta" onClick={() => onStart("free", options)} disabled={busy}>
          Práctica libre
        </button>
      </div>
    </div>
  );
}
