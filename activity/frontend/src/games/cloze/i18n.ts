// Cloze UI strings. Language preference and lookup are shared across games
// (src/i18n/lang.tsx); this file only owns the string tables.
import { type Lang, translate } from "../../i18n/lang";

export type { Lang };

// Cloze's default chrome language follows the selected deck: a learner drilling
// Spanish words (target="es") is learning Spanish, so the chrome defaults to
// English (their native language). The reverse for target="en".
export function defaultLangForTarget(target: string): Lang {
  return target === "en" ? "es" : "en";
}

/** Fallback when no deck is selected yet. */
export const DEFAULT_LANG: Lang = "en";

// ── string tables ──────────────────────────────────────────────────────────

const EN: Record<string, string> = {
  // setup
  "setup.title": "Cloze",
  "setup.tagline": "Fill in the missing word. 10 sentences per round.",
  "setup.practice.main": "Practice",
  "setup.practice.sub": "Random round · hints after misses",
  "setup.daily.main": "Daily — no hints until the end",
  "setup.daily.sub": "Same sentences for everyone · counts for your streak",
  "setup.or_customize": "or customize",
  "setup.language": "Language",
  "setup.level": "Level",
  "setup.mixed": "Mixed",
  "setup.answer_mode": "Answer mode",
  "setup.choice": "Multiple choice",
  "setup.type": "Type it",
  // round
  "round.finish": "Finish",
  "round.daily_tag": "Daily challenge",
  "round.progress": "{seq} / {total}",
  "round.daily_hint": "Corrections at the end",
  "round.placeholder": "write the word…",
  // feedback
  "feedback.correct": "Correct!",
  "feedback.retry_ok": "Got it: {answer}. Next!",
  "feedback.close": "Almost! {answer} (accents)",
  "feedback.close.short": "Almost! (accents)",
  "feedback.wrong": "Was {answer}",
  "feedback.wrong.short": "Incorrect",
  // retry (type mode)
  "retry.instruction": "Type it to continue",
  "retry.skip": "Skip",
  // continue (choice mode)
  "continue.instruction": "Sentence:",
  "miss.you_wrote": "You answered “{given}”.",
  "miss.try_again": "Not quite — copy the word from the sentence.",
  "continue.btn": "Continue",
  // summary
  "summary.verdict.90": "Flawless!",
  "summary.verdict.70": "Well done!",
  "summary.verdict.40": "Good work!",
  "summary.verdict.1": "Keep it up!",
  "summary.verdict.0": "Keep practicing!",
  "summary.correct": "correct",
  "summary.accuracy": "accuracy",
  "summary.best_streak": "best streak",
  "summary.review_title": "To review",
  "summary.sentence_label": "Sentence",
  "summary.practice_these": "Practise these {n}",
  "summary.play_again": "Play again",
  // lang toggle
  "lang.en": "EN",
  "lang.es": "ES",
};

const ES: Record<string, string> = {
  // setup
  "setup.title": "Cloze",
  "setup.tagline": "Completa la palabra que falta. 10 frases por ronda.",
  "setup.practice.main": "Práctica",
  "setup.practice.sub": "Ronda aleatoria · pistas después de los errores",
  "setup.daily.main": "Reto diario — sin pistas hasta el final",
  "setup.daily.sub": "Mismas frases para todos · cuenta para tu racha",
  "setup.or_customize": "o personaliza",
  "setup.language": "Idioma",
  "setup.level": "Nivel",
  "setup.mixed": "Mixto",
  "setup.answer_mode": "Tipo de respuesta",
  "setup.choice": "Opción múltiple",
  "setup.type": "Escribir",
  // round
  "round.finish": "Terminar",
  "round.daily_tag": "Reto diario",
  "round.progress": "{seq} / {total}",
  "round.daily_hint": "Revisa tus respuestas al final",
  "round.placeholder": "escribe la palabra…",
  // feedback
  "feedback.correct": "¡Correcto!",
  "feedback.retry_ok": "Eso es: {answer}. ¡Siguiente!",
  "feedback.close": "¡Casi! {answer} (acentos)",
  "feedback.close.short": "¡Casi! (acentos)",
  "feedback.wrong": "Era {answer}",
  "feedback.wrong.short": "Incorrecto",
  // retry (type mode)
  "retry.instruction": "Escríbela para continuar",
  "retry.skip": "Saltar",
  // continue (choice mode)
  "continue.instruction": "Frase:",
  "miss.you_wrote": "Respondiste «{given}».",
  "miss.try_again": "Casi — copia la palabra de la frase.",
  "continue.btn": "Continuar",
  // summary
  "summary.verdict.90": "¡Impecable!",
  "summary.verdict.70": "¡Muy bien!",
  "summary.verdict.40": "¡Bien hecho!",
  "summary.verdict.1": "¡Sigue así!",
  "summary.verdict.0": "¡A practicar!",
  "summary.correct": "correctas",
  "summary.accuracy": "precisión",
  "summary.best_streak": "mejor racha",
  "summary.review_title": "Para repasar",
  "summary.sentence_label": "Frase",
  "summary.practice_these": "Practicar {n}",
  "summary.play_again": "Jugar otra",
  // lang toggle
  "lang.en": "EN",
  "lang.es": "ES",
};

const TABLES: Record<Lang, Record<string, string>> = { en: EN, es: ES };

/** Look up a cloze UI string (see `translate` for fallback rules). */
export function t(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  return translate(TABLES, lang, key, vars);
}
