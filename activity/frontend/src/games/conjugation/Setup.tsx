import { useState } from "react";
import type { StartOptions } from "../../api";

interface SetupProps {
  onStart: (mode: "daily" | "free", options?: StartOptions) => void;
  busy: boolean;
  error: string | null;
}

// Option catalogs mirror the backend paradigm data (stable keys). The daily
// sprint ignores these — it's a fixed pool — so they only drive freeplay.
const VERB_SETS: { key: string; label: string }[] = [
  { key: "high-frequency", label: "Frecuentes" },
  { key: "regular-ar", label: "-AR" },
  { key: "regular-er-ir", label: "-ER / -IR" },
  { key: "irregulars", label: "Irregulares" },
];

const TENSES: { key: string; label: string }[] = [
  { key: "presente", label: "Presente" },
  { key: "pretérito", label: "Pretérito" },
  { key: "imperfecto", label: "Imperfecto" },
  { key: "futuro", label: "Futuro" },
];

const PRONOUNS: { key: string; label: string }[] = [
  { key: "yo", label: "yo" },
  { key: "tú", label: "tú" },
  { key: "él", label: "él" },
  { key: "nosotros", label: "nosotros" },
  { key: "vosotros", label: "vosotros" },
  { key: "ellos", label: "ellos" },
];

// Multi-select chip strip that guarantees at least one stays selected (an empty
// pool would be meaningless — the backend would silently fall back anyway, but
// we keep the UI honest).
function toggle(list: string[], key: string): string[] {
  if (list.includes(key)) {
    const next = list.filter((k) => k !== key);
    return next.length ? next : list; // never allow empty
  }
  return [...list, key];
}

export default function Setup({ onStart, busy, error }: SetupProps) {
  const [verbSet, setVerbSet] = useState("high-frequency");
  const [tenses, setTenses] = useState<string[]>(["presente", "pretérito"]);
  const [pronouns, setPronouns] = useState<string[]>([
    "yo",
    "tú",
    "él",
    "nosotros",
    "ellos",
  ]);

  const freeplay = (timed: boolean) =>
    onStart("free", { set: verbSet, tenses, pronouns, timed });

  return (
    <div className="conj conj-setup">
      <div className="setup-lede">
        <h1 className="setup-title">Conjugación</h1>
        <p className="muted">
          Conjuga tantos verbos como puedas en <strong>60 segundos</strong>.
        </p>
      </div>

      <button className="cta cta-daily" onClick={() => onStart("daily")} disabled={busy}>
        <span className="cta-daily-main">Reto diario</span>
        <span className="cta-daily-sub">Mismo set para todos · cuenta para tu racha</span>
      </button>

      <div className="setup-divider">
        <span>o personaliza</span>
      </div>

      <fieldset className="setup-group">
        <legend>Verbos</legend>
        <div className="chips">
          {VERB_SETS.map((s) => (
            <button
              key={s.key}
              className={`chip${verbSet === s.key ? " chip--on" : ""}`}
              onClick={() => setVerbSet(s.key)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="setup-group">
        <legend>Tiempos</legend>
        <div className="chips">
          {TENSES.map((t) => (
            <button
              key={t.key}
              className={`chip${tenses.includes(t.key) ? " chip--on" : ""}`}
              onClick={() => setTenses((cur) => toggle(cur, t.key))}
            >
              {t.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="setup-group">
        <legend>Pronombres</legend>
        <div className="chips">
          {PRONOUNS.map((p) => (
            <button
              key={p.key}
              className={`chip${pronouns.includes(p.key) ? " chip--on" : ""}`}
              onClick={() => setPronouns((cur) => toggle(cur, p.key))}
            >
              {p.label}
            </button>
          ))}
        </div>
      </fieldset>

      {/* Reserved slot: the error occupies fixed space whether or not it's
          shown, so revealing it never pushes the action buttons down. */}
      <div className="setup-error-slot">{error && <p className="error">{error}</p>}</div>

      <div className="setup-actions">
        <button className="cta" onClick={() => freeplay(true)} disabled={busy}>
          Sprint 60s
        </button>
        <button className="cta cta-ghost" onClick={() => freeplay(false)} disabled={busy}>
          Práctica libre ↻
        </button>
      </div>
      <p className="muted setup-hint">
        La práctica libre no tiene reloj: termina cuando quieras.
      </p>
    </div>
  );
}
