import { useState } from "react";
import type { StartOptions } from "../../api";

interface SetupProps {
  onStart: (mode: "daily" | "free", options?: StartOptions) => void;
  busy: boolean;
  error: string | null;
}

// The learner's target language = which sentence gets the blank. "es" for
// Spanish learners (Spanish word hidden, English shown as context), "en" for
// English learners (the mirror). Keys match the backend deck keys.
const TARGETS: { key: string; label: string; sub: string }[] = [
  { key: "es", label: "Español", sub: "Aprendo español" },
  { key: "en", label: "English", sub: "I'm learning English" },
];

const DIFFICULTIES: { key: string; label: string }[] = [
  { key: "beginner", label: "Principiante" },
  { key: "intermediate", label: "Intermedio" },
  { key: "advanced", label: "Avanzado" },
];

const ANSWER_MODES: { key: "choice" | "type"; label: string }[] = [
  { key: "choice", label: "Opción múltiple" },
  { key: "type", label: "Escribir" },
];

export default function Setup({ onStart, busy, error }: SetupProps) {
  const [target, setTarget] = useState("es");
  // null = mixed / all difficulties.
  const [difficulty, setDifficulty] = useState<string | null>(null);
  const [answerMode, setAnswerMode] = useState<"choice" | "type">("choice");

  const options: StartOptions = {
    target,
    answer_mode: answerMode,
    ...(difficulty ? { difficulty } : {}),
  };

  return (
    <div className="cloze cloze-setup">
      <div className="setup-lede">
        <h1 className="setup-title">Cloze</h1>
        <p className="muted">
          Completa la palabra que falta. <strong>10 frases</strong> por ronda.
        </p>
      </div>

      <button
        className="cta cta-daily"
        onClick={() => onStart("daily", { target, answer_mode: answerMode })}
        disabled={busy}
      >
        <span className="cta-daily-main">Reto diario</span>
        <span className="cta-daily-sub">Mismas frases para todos · cuenta para tu racha</span>
      </button>

      <div className="setup-divider">
        <span>o personaliza</span>
      </div>

      <fieldset className="setup-group">
        <legend>Idioma</legend>
        <div className="chips">
          {TARGETS.map((t) => (
            <button
              key={t.key}
              className={`chip${target === t.key ? " chip--on" : ""}`}
              onClick={() => setTarget(t.key)}
              title={t.sub}
            >
              {t.label}
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

      {/* Reserved slot: the error occupies fixed space whether shown or not. */}
      <div className="setup-error-slot">{error && <p className="error">{error}</p>}</div>

      <div className="setup-actions">
        <button className="cta" onClick={() => onStart("free", options)} disabled={busy}>
          Práctica libre
        </button>
      </div>
    </div>
  );
}
