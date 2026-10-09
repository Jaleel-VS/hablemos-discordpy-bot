// Shared UI-language preference for every game's chrome (labels, buttons,
// feedback). The *learning content* is never translated by this — a Spanish
// sentence stays Spanish — only the interface around it.
//
// Tri-state on purpose: `null` means the player never chose, so each game
// applies its own audience default (Wordle/Conjugation → English for Spanish
// learners; Phrasal → Spanish for English learners; Cloze follows the deck).
// Once the player toggles anywhere, that choice wins in every game.
import { useState } from "react";

export type Lang = "en" | "es";

const STORAGE_KEY = "hablemos.lang";
/** Conjugation stored its own key before this module existed. */
const LEGACY_KEY = "conj.lang";

function parse(value: string | null): Lang | null {
  return value === "en" || value === "es" ? value : null;
}

/** The player's explicit choice, or null if they never toggled. */
export function storedLang(): Lang | null {
  const current = parse(localStorage.getItem(STORAGE_KEY));
  if (current !== null) return current;
  // One-time migration: carry the old conjugation toggle over, then drop it.
  const legacy = parse(localStorage.getItem(LEGACY_KEY));
  localStorage.removeItem(LEGACY_KEY);
  if (legacy !== null) localStorage.setItem(STORAGE_KEY, legacy);
  return legacy;
}

export function setLang(lang: Lang): void {
  localStorage.setItem(STORAGE_KEY, lang);
}

/**
 * React state for a screen's chrome language: the stored choice, else the
 * game's audience default. The setter persists, so every game follows.
 */
export function useLang(fallback: Lang): [Lang, (lang: Lang) => void] {
  const [lang, setState] = useState<Lang>(() => storedLang() ?? fallback);
  return [
    lang,
    (next: Lang) => {
      setLang(next);
      setState(next);
    },
  ];
}

/**
 * Look up a UI string from a game's tables, substituting `{key}` placeholders.
 * Falls back to EN, then to the key itself, so a missing translation is
 * visible in review rather than blank.
 */
export function translate(
  tables: Record<Lang, Record<string, string>>,
  lang: Lang,
  key: string,
  vars?: Record<string, string | number>,
): string {
  const value = tables[lang][key] ?? tables.en[key] ?? key;
  if (!vars) return value;
  return value.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? ""));
}

interface LangToggleProps {
  lang: Lang;
  onChange: (lang: Lang) => void;
}

/** EN | ES segmented switch, top-right of a setup screen. */
export function LangToggle({ lang, onChange }: LangToggleProps) {
  return (
    <div className="lang-toggle" role="group" aria-label="Interface language / Idioma">
      {(["en", "es"] as const).map((l) => (
        <button
          key={l}
          className={`lang-btn${lang === l ? " lang-btn--on" : ""}`}
          aria-pressed={lang === l}
          onClick={() => onChange(l)}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
