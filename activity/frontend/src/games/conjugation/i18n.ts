// Minimal i18n for the conjugation game. All UI copy goes through `t()`.
// Language is persisted in localStorage so it survives Discord Activity restarts.

export type Lang = "en" | "es";

const STORAGE_KEY = "conj.lang";

export function getLang(): Lang {
  return localStorage.getItem(STORAGE_KEY) === "es" ? "es" : "en";
}

export function setLang(lang: Lang): void {
  localStorage.setItem(STORAGE_KEY, lang);
}

export interface TenseMeta {
  label: string;
  english: string;
}

/** EN: "Preterite (pretérito)"  ES: "Pretérito" */
export function tenseLabel(lang: Lang, meta: TenseMeta): string {
  if (lang === "es") return meta.label;
  if (meta.english && meta.english !== meta.label) {
    return `${meta.english} (${meta.label})`;
  }
  return meta.label;
}

// ── string tables ──────────────────────────────────────────────────────────

const EN: Record<string, string> = {
  // setup
  "setup.title": "Conjugation",
  "setup.tagline": "How many verbs can you conjugate?",
  "setup.daily.main": "Daily challenge",
  "setup.daily.sub": "Same set for everyone · counts for your streak · 60s sprint",
  "setup.or_customize": "or customize",
  "setup.verbs": "Verbs",
  "setup.tenses": "Tenses",
  "setup.pronouns": "Pronouns",
  "setup.options": "Options",
  "setup.strict": "Strict accents",
  "setup.strict.hint": "Accent errors count as wrong, not close",
  "setup.variants": "Show usted / ustedes / ella",
  "setup.sprint": "Sprint 60s",
  "setup.practice": "Practice",
  "setup.items.label": "Questions",
  "setup.practice.hint": "Untimed — stop any time.",
  "setup.form.hint": "Type only the verb form, e.g. hablo — not yo hablo",
  "setup.loading": "Loading…",
  // sprint
  "sprint.placeholder": "type the conjugation…",
  "sprint.skip": "Skip",
  "sprint.finish": "Finish",
  "sprint.format.hint": "Type only the verb form, e.g. hablo",
  "sprint.progress": "{done} / {total}",
  // feedback
  "feedback.exact": "Correct!",
  "feedback.close": "Almost! (accent)",
  "feedback.close.expected": "Almost! {expected} (accent)",
  "feedback.close.strict": "Accent required — counted as wrong",
  "feedback.close.strict.expected": "Accent required: {expected}",
  "feedback.wrong": "Wrong",
  "feedback.wrong.expected": "Was {expected}",
  "feedback.skipped": "Skipped",
  "feedback.retry.ok": "Got it: {expected}. Next!",
  "feedback.retry.moveon": "It's {expected} — we'll come back to it. Next!",
  // retry card
  "retry.instruction": "Type it to continue",
  // summary
  "summary.verdict.20": "Unstoppable!",
  "summary.verdict.12": "Excellent!",
  "summary.verdict.6": "Well done!",
  "summary.verdict.1": "Keep it up!",
  "summary.verdict.0": "Keep practicing!",
  "summary.correct": "correct",
  "summary.accuracy": "accuracy",
  "summary.best_streak": "best streak",
  "summary.attempts": "attempts",
  "summary.close": "accent slips",
  "summary.skipped": "skipped",
  "summary.breakdown": "Breakdown",
  "summary.breakdown.tenses": "By tense",
  "summary.breakdown.pronouns": "By pronoun",
  "summary.misses.title": "To review",
  "summary.practice_verbs": "Practise these {n} verbs",
  "summary.play_again": "Play again",
  "summary.grid": "Today's run",
  // lang toggle
  "lang.en": "EN",
  "lang.es": "ES",
};

const ES: Record<string, string> = {
  // setup
  "setup.title": "Conjugación",
  "setup.tagline": "¿Cuántos verbos puedes conjugar?",
  "setup.daily.main": "Reto diario",
  "setup.daily.sub": "Mismo set para todos · cuenta para tu racha · 60s",
  "setup.or_customize": "o personaliza",
  "setup.verbs": "Verbos",
  "setup.tenses": "Tiempos",
  "setup.pronouns": "Pronombres",
  "setup.options": "Opciones",
  "setup.strict": "Acentos estrictos",
  "setup.strict.hint": "Los errores de acento cuentan como fallo",
  "setup.variants": "Mostrar usted / ustedes / ella",
  "setup.sprint": "Sprint 60s",
  "setup.practice": "Práctica",
  "setup.items.label": "Preguntas",
  "setup.practice.hint": "Sin reloj — termina cuando quieras.",
  "setup.form.hint": "Escribe solo la forma verbal, p.ej. hablo — no yo hablo",
  "setup.loading": "Cargando…",
  // sprint
  "sprint.placeholder": "escribe la conjugación…",
  "sprint.skip": "Saltar",
  "sprint.finish": "Terminar",
  "sprint.format.hint": "Escribe solo la forma verbal, p.ej. hablo",
  "sprint.progress": "{done} / {total}",
  // feedback
  "feedback.exact": "¡Correcto!",
  "feedback.close": "¡Casi! (acento)",
  "feedback.close.expected": "¡Casi! {expected} (acento)",
  "feedback.close.strict": "Acento requerido — contado como fallo",
  "feedback.close.strict.expected": "Acento requerido: {expected}",
  "feedback.wrong": "Incorrecto",
  "feedback.wrong.expected": "Era {expected}",
  "feedback.skipped": "Saltado",
  "feedback.retry.ok": "Eso es: {expected}. ¡Siguiente!",
  "feedback.retry.moveon": "Es {expected} — volveremos a verlo. ¡Siguiente!",
  // retry card
  "retry.instruction": "Escríbelo para continuar",
  // summary
  "summary.verdict.20": "¡Imparable!",
  "summary.verdict.12": "¡Excelente!",
  "summary.verdict.6": "¡Bien hecho!",
  "summary.verdict.1": "¡Sigue así!",
  "summary.verdict.0": "¡A practicar!",
  "summary.correct": "correctas",
  "summary.accuracy": "precisión",
  "summary.best_streak": "mejor racha",
  "summary.attempts": "intentos",
  "summary.close": "acentos",
  "summary.skipped": "saltados",
  "summary.breakdown": "Desglose",
  "summary.breakdown.tenses": "Por tiempo",
  "summary.breakdown.pronouns": "Por pronombre",
  "summary.misses.title": "Para repasar",
  "summary.practice_verbs": "Practicar estos {n} verbos",
  "summary.play_again": "Jugar otra",
  "summary.grid": "Tu partida de hoy",
  // lang toggle
  "lang.en": "EN",
  "lang.es": "ES",
};

const TABLES: Record<Lang, Record<string, string>> = { en: EN, es: ES };

/**
 * Look up a UI string, substituting `{key}` placeholders from `vars`.
 * Falls back to EN then to the raw key if a translation is missing.
 */
export function t(
  lang: Lang,
  key: string,
  vars?: Record<string, string | number>,
): string {
  const val = TABLES[lang][key] ?? EN[key] ?? key;
  if (!vars) return val;
  return val.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
}
