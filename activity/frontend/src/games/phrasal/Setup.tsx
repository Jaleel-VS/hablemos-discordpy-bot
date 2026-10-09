import { useState } from "react";
import type { StartOptions } from "../../api";
import { useLang } from "../../i18n/lang";
import { LangToggle } from "../../i18n/lang";
import { DEFAULT_LANG, t } from "./i18n";

interface SetupProps {
  onStart: (mode: "daily" | "free", options?: StartOptions) => void;
  onLearn: () => void;
  busy: boolean;
  error: string | null;
}

// UI is Spanish (the community is Spanish natives learning English); the
// CONTENT (the phrasal verbs) is English.

export default function Setup({ onStart, onLearn, busy, error }: SetupProps) {
  const [lang, setLang] = useLang(DEFAULT_LANG);
  const [difficulty, setDifficulty] = useState<string | null>(null);
  const [blankMode, setBlankMode] = useState<"particle" | "whole">("particle");
  const [answerMode, setAnswerMode] = useState<"choice" | "type">("choice");

  const options: StartOptions = {
    blank_mode: blankMode,
    answer_mode: answerMode,
    ...(difficulty ? { difficulty } : {}),
  };

  const BLANK_MODES: { key: "particle" | "whole"; label: string; sub: string }[] = [
    { key: "particle", label: t(lang, "setup.blank.particle"), sub: t(lang, "setup.blank.particle.sub") },
    { key: "whole",    label: t(lang, "setup.blank.whole"),    sub: t(lang, "setup.blank.whole.sub") },
  ];

  const ANSWER_MODES: { key: "choice" | "type"; label: string }[] = [
    { key: "choice", label: t(lang, "setup.answer.choice") },
    { key: "type",   label: t(lang, "setup.answer.type") },
  ];

  const DIFFICULTIES: { key: string; label: string }[] = [
    { key: "beginner",     label: t(lang, "setup.diff.beginner") },
    { key: "intermediate", label: t(lang, "setup.diff.intermediate") },
    { key: "advanced",     label: t(lang, "setup.diff.advanced") },
  ];

  return (
    <div className="phrasal phrasal-setup">
      <div className="setup-header">
        <div className="setup-lede">
          <h1 className="setup-title">{t(lang, "setup.title")}</h1>
          <p className="muted">{t(lang, "setup.tagline")}</p>
        </div>
        <LangToggle lang={lang} onChange={setLang} />
      </div>

      {/* 1. Aprender — entry point for beginners; kept prominent at top. */}
      <button className="cta cta-learn" onClick={onLearn} disabled={busy}>
        <span className="cta-main">{t(lang, "setup.learn")}</span>
        <span className="cta-sub">{t(lang, "setup.learn.sub")}</span>
      </button>

      {/* 2. Freeplay config + primary CTA */}
      <fieldset className="setup-group">
        <legend>{t(lang, "setup.blank_mode")}</legend>
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
        <legend>{t(lang, "setup.answer_mode")}</legend>
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

      <fieldset className="setup-group">
        <legend>{t(lang, "setup.difficulty")}</legend>
        <div className="chips">
          <button
            className={`chip${difficulty === null ? " chip--on" : ""}`}
            onClick={() => setDifficulty(null)}
          >
            {t(lang, "setup.diff.all")}
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

      <div className="setup-error-slot">{error && <p className="error">{error}</p>}</div>

      <div className="setup-actions">
        <button className="cta cta-primary" onClick={() => onStart("free", options)} disabled={busy}>
          {t(lang, "setup.free.cta")}
        </button>
      </div>

      {/* 3. Daily — prominent but below freeplay; labelled with anti-hint note. */}
      <button
        className="cta cta-daily"
        onClick={() => onStart("daily", { blank_mode: blankMode, answer_mode: answerMode })}
        disabled={busy}
      >
        <span className="cta-main">{t(lang, "setup.daily.cta")}</span>
        <span className="cta-sub">{t(lang, "setup.daily.sub")}</span>
      </button>
    </div>
  );
}
