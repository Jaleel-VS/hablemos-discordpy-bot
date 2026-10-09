import { useState } from "react";
import type { StartOptions } from "../../api";
import type { Lang } from "../../i18n/lang";
import { LangToggle, setLang, storedLang } from "../../i18n/lang";
import { defaultLangForTarget, t } from "./i18n";
interface SetupProps {
  onStart: (mode: "daily" | "free", options?: StartOptions) => void;
  busy: boolean;
  error: string | null;
}

// The learner's target language = which sentence gets the blank. "es" for
// Spanish learners (Spanish word hidden, English shown as context), "en" for
// English learners (the mirror). Keys match the backend deck keys.
const TARGETS: { key: string; labelEN: string; labelES: string; sub: string }[] = [
  { key: "es", labelEN: "Español", labelES: "Español", sub: "I'm learning Spanish" },
  { key: "en", labelEN: "English", labelES: "Inglés", sub: "I'm learning English" },
];

const DIFFICULTIES: { key: string; labelEN: string; labelES: string }[] = [
  { key: "beginner", labelEN: "Beginner", labelES: "Principiante" },
  { key: "intermediate", labelEN: "Intermediate", labelES: "Intermedio" },
  { key: "advanced", labelEN: "Advanced", labelES: "Avanzado" },
];

export default function Setup({ onStart, busy, error }: SetupProps) {
  const [target, setTarget] = useState("es");
  // null = mixed / all difficulties.
  const [difficulty, setDifficulty] = useState<string | null>(null);
  const [answerMode, setAnswerMode] = useState<"choice" | "type">("choice");

  // Chrome language: follow the deck default when the player never chose.
  // storedLang() is null when the player never toggled, so recompute the
  // fallback whenever the target changes. useLang initialises once from
  // storage, so we do not use it here — we manage lang state directly.
  const [lang, setLangState] = useState(() => storedLang() ?? defaultLangForTarget(target));

  // When target changes, update lang fallback only if the player never chose.
  function handleTargetChange(newTarget: string) {
    setTarget(newTarget);
    if (storedLang() === null) {
      setLangState(defaultLangForTarget(newTarget));
    }
  }

  function handleLangChange(next: Lang) {
    setLang(next);
    setLangState(next);
  }


  const options: StartOptions = {
    target,
    answer_mode: answerMode,
    ...(difficulty ? { difficulty } : {}),
  };

  return (
    <div className="cloze cloze-setup">
      <LangToggle lang={lang} onChange={handleLangChange} />
      <div className="setup-lede">
        <h1 className="setup-title">{t(lang, "setup.title")}</h1>
        <p className="muted">{t(lang, "setup.tagline")}</p>
      </div>

      {/* Choices first, then the buttons that use them: a Practice button above
          its own options starts a round before the player picks anything. */}
      <fieldset className="setup-group">
        <legend>{t(lang, "setup.language")}</legend>
        <div className="chips">
          {TARGETS.map((tgt) => (
            <button
              key={tgt.key}
              className={`chip${target === tgt.key ? " chip--on" : ""}`}
              onClick={() => handleTargetChange(tgt.key)}
              title={tgt.sub}
            >
              {lang === "es" ? tgt.labelES : tgt.labelEN}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="setup-group">
        <legend>{t(lang, "setup.level")}</legend>
        <div className="chips">
          <button
            className={`chip${difficulty === null ? " chip--on" : ""}`}
            onClick={() => setDifficulty(null)}
          >
            {t(lang, "setup.mixed")}
          </button>
          {DIFFICULTIES.map((dfc) => (
            <button
              key={dfc.key}
              className={`chip${difficulty === dfc.key ? " chip--on" : ""}`}
              onClick={() => setDifficulty(dfc.key)}
            >
              {lang === "es" ? dfc.labelES : dfc.labelEN}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="setup-group">
        <legend>{t(lang, "setup.answer_mode")}</legend>
        <div className="chips">
          {(["choice", "type"] as const).map((m) => (
            <button
              key={m}
              className={`chip${answerMode === m ? " chip--on" : ""}`}
              onClick={() => setAnswerMode(m)}
            >
              {t(lang, m === "choice" ? "setup.choice" : "setup.type")}
            </button>
          ))}
        </div>
      </fieldset>

      {/* Reserved slot: the error occupies fixed space whether shown or not. */}
      <div className="setup-error-slot">{error && <p className="error">{error}</p>}</div>

      <div className="setup-actions setup-actions--stack">
        <button className="cta cta-stack" onClick={() => onStart("free", options)} disabled={busy}>
          <span className="cta-main">{t(lang, "setup.practice.main")}</span>
          <span className="cta-sub">{t(lang, "setup.practice.sub")}</span>
        </button>
        {/* Daily: fixed sentences, ignores level, keeps language + answer mode. */}
        <button
          className="cta cta-daily"
          onClick={() => onStart("daily", { target, answer_mode: answerMode })}
          disabled={busy}
        >
          <span className="cta-daily-main">{t(lang, "setup.daily.main")}</span>
          <span className="cta-daily-sub">{t(lang, "setup.daily.sub")}</span>
        </button>
      </div>
    </div>
  );
}
