import { useEffect, useRef, useState } from "react";
import {
  fetchConjugationCatalog,
  type ConjugationCatalog,
  type ConjugationSetInfo,
  type ConjugationTenseInfo,
  type StartOptions,
} from "../../api";
import { getLang, setLang, t, tenseLabel, type Lang } from "./i18n";

interface SetupProps {
  onStart: (mode: "daily" | "free", options?: StartOptions) => void;
  busy: boolean;
  error: string | null;
}

// Fallback catalog used when the fetch fails so the screen never blocks.
const FALLBACK_TENSES: ConjugationTenseInfo[] = [
  { key: "presente", label: "Presente", english: "Present", hint: "Ongoing / habitual actions", example: "hablo" },
  { key: "pretérito", label: "Pretérito", english: "Preterite", hint: "Completed past actions", example: "hablé" },
  { key: "imperfecto", label: "Imperfecto", english: "Imperfect", hint: "Ongoing or habitual past", example: "hablaba" },
  { key: "futuro", label: "Futuro", english: "Future", hint: "Future actions", example: "hablaré" },
];

const FALLBACK_SETS: ConjugationSetInfo[] = [
  { key: "high-frequency", label: "High-frequency", size: 50 },
  { key: "regular-ar", label: "-AR", size: 40 },
  { key: "regular-er-ir", label: "-ER / -IR", size: 30 },
  { key: "irregulars", label: "Irregulars", size: 40 },
];

const FALLBACK_PRONOUNS = [
  { key: "yo", english: "I" },
  { key: "tú", english: "you (informal)" },
  { key: "él", english: "he / she / it" },
  { key: "nosotros", english: "we" },
  { key: "vosotros", english: "you all (Spain)" },
  { key: "ellos", english: "they" },
];

// Multi-select chip strip that guarantees at least one stays selected.
function toggle(list: string[], key: string): string[] {
  if (list.includes(key)) {
    const next = list.filter((k) => k !== key);
    return next.length ? next : list; // never allow empty
  }
  return [...list, key];
}

type PracticeItems = 10 | 20 | 0;

export default function Setup({ onStart, busy, error }: SetupProps) {
  const [lang, setLangState] = useState<Lang>(getLang());
  const [catalog, setCatalog] = useState<ConjugationCatalog | null>(null);
  const [verbSet, setVerbSet] = useState("high-frequency");
  const [tenses, setTenses] = useState<string[]>(["presente", "pretérito"]);
  const [pronouns, setPronouns] = useState<string[]>([
    "yo", "tú", "él", "nosotros", "ellos",
  ]);
  const [strict, setStrict] = useState(false);
  const [variants, setVariants] = useState(false);
  const [practiceItems, setPracticeItems] = useState<PracticeItems>(20);
  // Which tense chip has the info popover open.
  const [openInfo, setOpenInfo] = useState<string | null>(null);
  const infoRef = useRef<HTMLFieldSetElement>(null);

  // Load catalog; fall back silently on error.
  useEffect(() => {
    fetchConjugationCatalog()
      .then(setCatalog)
      .catch(() => {/* use fallback */});
  }, []);

  // Close the tense popover when clicking outside it.
  useEffect(() => {
    if (!openInfo) return;
    const handler = (e: MouseEvent) => {
      if (infoRef.current && !infoRef.current.contains(e.target as Node)) {
        setOpenInfo(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [openInfo]);

  const tenseList = catalog?.tenses ?? FALLBACK_TENSES;
  const pronounList = catalog?.pronouns ?? FALLBACK_PRONOUNS;
  const setList = catalog?.sets ?? FALLBACK_SETS;

  const switchLang = (l: Lang) => {
    setLang(l);
    setLangState(l);
  };

  const freeplay = (timed: boolean, items: number) =>
    onStart("free", { set: verbSet, tenses, pronouns, timed, strict, variants, items });

  return (
    <div className="conj conj-setup">
    <div className="conj-inner">
      {/* Language toggle */}
      <div className="lang-toggle">
        <button
          className={`lang-btn${lang === "en" ? " lang-btn--on" : ""}`}
          onClick={() => switchLang("en")}
          aria-pressed={lang === "en"}
        >
          {t(lang, "lang.en")}
        </button>
        <button
          className={`lang-btn${lang === "es" ? " lang-btn--on" : ""}`}
          onClick={() => switchLang("es")}
          aria-pressed={lang === "es"}
        >
          {t(lang, "lang.es")}
        </button>
      </div>

      <div className="setup-lede">
        <h1 className="setup-title">{t(lang, "setup.title")}</h1>
        <p className="muted">{t(lang, "setup.tagline")}</p>
      </div>

      <button className="cta cta-daily" onClick={() => onStart("daily")} disabled={busy}>
        <span className="cta-daily-main">{t(lang, "setup.daily.main")}</span>
        <span className="cta-daily-sub">{t(lang, "setup.daily.sub")}</span>
      </button>

      <div className="setup-divider">
        <span>{t(lang, "setup.or_customize")}</span>
      </div>

      {/* Verb set */}
      <fieldset className="setup-group">
        <legend>{t(lang, "setup.verbs")}</legend>
        <div className="chips">
          {setList.map((s) => (
            <button
              key={s.key}
              className={`chip${verbSet === s.key ? " chip--on" : ""}`}
              onClick={() => setVerbSet(s.key)}
            >
              {s.label}
              {s.size ? <span className="chip-sub">{s.size}</span> : null}
            </button>
          ))}
        </div>
      </fieldset>

      {/* Tenses with info popovers */}
      <fieldset className="setup-group" ref={infoRef}>
        <legend>{t(lang, "setup.tenses")}</legend>
        <div className="chips">
          {tenseList.map((ten) => (
            <div key={ten.key} className="chip-wrap">
              <button
                className={`chip${tenses.includes(ten.key) ? " chip--on" : ""}`}
                onClick={() => setTenses((cur) => toggle(cur, ten.key))}
              >
                {tenseLabel(lang, ten)}
              </button>
              <button
                className="chip-info-btn"
                aria-label={`Info about ${ten.english || ten.label}`}
                onClick={(e) => {
                  e.stopPropagation();
                  setOpenInfo(openInfo === ten.key ? null : ten.key);
                }}
              >
                ?
              </button>
              {openInfo === ten.key && (
                <div className="chip-info" role="tooltip">
                  <p className="chip-info-hint">{ten.hint}</p>
                  {ten.example && (
                    <p className="chip-info-example">
                      e.g. <strong>{ten.example}</strong>
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </fieldset>

      {/* Pronouns */}
      <fieldset className="setup-group">
        <legend>{t(lang, "setup.pronouns")}</legend>
        <div className="chips">
          {pronounList.map((p) => (
            <button
              key={p.key}
              className={`chip${pronouns.includes(p.key) ? " chip--on" : ""}`}
              onClick={() => setPronouns((cur) => toggle(cur, p.key))}
            >
              {p.key}
              {p.english && <span className="chip-sub">{p.english}</span>}
            </button>
          ))}
        </div>
      </fieldset>

      {/* Options toggles */}
      <fieldset className="setup-group">
        <legend>{t(lang, "setup.options")}</legend>
        <div className="toggles">
          <label className="toggle">
            <input
              type="checkbox"
              checked={strict}
              onChange={(e) => setStrict(e.target.checked)}
            />
            <span className="toggle-label">
              {t(lang, "setup.strict")}
              <span className="toggle-hint">{t(lang, "setup.strict.hint")}</span>
            </span>
          </label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={variants}
              onChange={(e) => setVariants(e.target.checked)}
            />
            <span className="toggle-label">{t(lang, "setup.variants")}</span>
          </label>
        </div>
      </fieldset>

      <div className="setup-error-slot">{error && <p className="error">{error}</p>}</div>

      <div className="setup-actions">
        <button className="cta" onClick={() => freeplay(true, 0)} disabled={busy}>
          {t(lang, "setup.sprint")}
        </button>
        <div className="setup-practice-group">
          <button
            className="cta cta-ghost setup-practice-btn"
            onClick={() => freeplay(false, practiceItems)}
            disabled={busy}
          >
            {t(lang, "setup.practice")}
          </button>
          <div className="segmented" role="group" aria-label={t(lang, "setup.items.label")}>
            {([10, 20, 0] as PracticeItems[]).map((n) => (
              <button
                key={n}
                className={`segmented-btn${practiceItems === n ? " segmented-btn--on" : ""}`}
                onClick={() => setPracticeItems(n)}
                aria-pressed={practiceItems === n}
              >
                {n === 0 ? "∞" : n}
              </button>
            ))}
          </div>
        </div>
      </div>

      <p className="muted setup-hint">{t(lang, "setup.practice.hint")}</p>
    </div>
    </div>
  );
}
