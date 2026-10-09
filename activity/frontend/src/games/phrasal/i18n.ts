// Phrasal-verb game UI strings.
// Language preference and lookup are shared across games (src/i18n/lang.tsx);
// this file only owns the string tables.
import { type Lang, translate } from "../../i18n/lang";

export type { Lang };

/** Phrasal's audience is Spanish natives learning English → default ES. */
export const DEFAULT_LANG: Lang = "es";

// ── string tables ──────────────────────────────────────────────────────────

const ES: Record<string, string> = {
  // setup
  "setup.title": "Phrasal Verbs",
  "setup.tagline": "¿Conoces estos verbos?",
  "setup.learn": "Aprender",
  "setup.learn.sub": "Explora el vocabulario antes de practicar",
  "setup.free.cta": "Práctica libre",
  "setup.daily.cta": "Reto diario",
  "setup.daily.sub": "Sin pistas hasta el final",
  "setup.or": "o",
  "setup.blank_mode": "Qué completas",
  "setup.blank.particle": "Partícula",
  "setup.blank.particle.sub": "look ___ → up",
  "setup.blank.whole": "Verbo completo",
  "setup.blank.whole.sub": "I need to ___ → look up",
  "setup.answer_mode": "Cómo responder",
  "setup.answer.choice": "Opción múltiple",
  "setup.answer.type": "Escribir",
  "setup.difficulty": "Dificultad",
  "setup.diff.all": "Mixto",
  "setup.diff.beginner": "Principiante",
  "setup.diff.intermediate": "Intermedio",
  "setup.diff.advanced": "Avanzado",
  "setup.loading": "Cargando…",
  // exercise
  "exercise.daily.tag": "Reto diario — sin pistas hasta el final",
  "exercise.finish": "Terminar",
  "exercise.progress": "{done} / {total}",
  "exercise.placeholder.particle": "partícula…",
  "exercise.placeholder.whole": "verbo con partícula…",
  "exercise.def.en_disclosure": "Definición en inglés",
  "exercise.daily.hint": "Revisa tus respuestas al final",
  "exercise.feedback.exact": "¡Correcto!",
  "exercise.feedback.retry_ok": "Got it: {answer}. Next!",
  "exercise.feedback.close": "¡Casi! Era {answer}",
  "exercise.feedback.wrong": "Era {answer}",
  "exercise.feedback.retry": "Escríbelo para continuar",
  "exercise.feedback.retry.moveon": "Era {answer} — inténtalo de nuevo",
  "exercise.continue": "Continuar →",
  // summary
  "summary.verdict.90": "¡Impecable!",
  "summary.verdict.70": "¡Muy bien!",
  "summary.verdict.40": "¡Bien hecho!",
  "summary.verdict.1": "¡Sigue así!",
  "summary.verdict.0": "¡A practicar!",
  "summary.correct": "correctas",
  "summary.accuracy": "precisión",
  "summary.best_streak": "mejor racha",
  "summary.misses.title": "Para repasar",
  "summary.practice_n": "Practicar estos {n}",
  "summary.play_again": "Jugar otra",
  // learn
  "learn.back": "← Atrás",
  "learn.loading": "Cargando…",
  "learn.error": "No se pudo cargar",
  "learn.prev": "← Anterior",
  "learn.next": "Siguiente →",
  "learn.practice_10": "Practicar estos 10",
  "learn.filter.all": "Todos",
  "learn.filter.beginner": "Principiante",
  "learn.filter.intermediate": "Intermedio",
  "learn.filter.advanced": "Avanzado",
  // shared
  "lang.en": "EN",
  "lang.es": "ES",
};

const EN: Record<string, string> = {
  // setup
  "setup.title": "Phrasal Verbs",
  "setup.tagline": "Test your knowledge of phrasal verbs",
  "setup.learn": "Learn",
  "setup.learn.sub": "Browse vocabulary before practicing",
  "setup.free.cta": "Free practice",
  "setup.daily.cta": "Daily challenge",
  "setup.daily.sub": "No hints until the end",
  "setup.or": "or",
  "setup.blank_mode": "What to blank",
  "setup.blank.particle": "Particle",
  "setup.blank.particle.sub": "look ___ → up",
  "setup.blank.whole": "Whole verb",
  "setup.blank.whole.sub": "I need to ___ → look up",
  "setup.answer_mode": "How to answer",
  "setup.answer.choice": "Multiple choice",
  "setup.answer.type": "Type",
  "setup.difficulty": "Difficulty",
  "setup.diff.all": "Mixed",
  "setup.diff.beginner": "Beginner",
  "setup.diff.intermediate": "Intermediate",
  "setup.diff.advanced": "Advanced",
  "setup.loading": "Loading…",
  // exercise
  "exercise.daily.tag": "Daily — no hints until the end",
  "exercise.finish": "Finish",
  "exercise.progress": "{done} / {total}",
  "exercise.placeholder.particle": "particle…",
  "exercise.placeholder.whole": "phrasal verb…",
  "exercise.def.en_disclosure": "English definition",
  "exercise.daily.hint": "See your answers at the end",
  "exercise.feedback.exact": "Correct!",
  "exercise.feedback.retry_ok": "Eso es: {answer}. ¡Siguiente!",
  "exercise.feedback.close": "Almost! It's {answer}",
  "exercise.feedback.wrong": "It was {answer}",
  "exercise.feedback.retry": "Type it to continue",
  "exercise.feedback.retry.moveon": "It's {answer} — try again",
  "exercise.continue": "Continue →",
  // summary
  "summary.verdict.90": "Flawless!",
  "summary.verdict.70": "Great job!",
  "summary.verdict.40": "Well done!",
  "summary.verdict.1": "Keep it up!",
  "summary.verdict.0": "Keep practicing!",
  "summary.correct": "correct",
  "summary.accuracy": "accuracy",
  "summary.best_streak": "best streak",
  "summary.misses.title": "To review",
  "summary.practice_n": "Practice these {n}",
  "summary.play_again": "Play again",
  // learn
  "learn.back": "← Back",
  "learn.loading": "Loading…",
  "learn.error": "Could not load",
  "learn.prev": "← Prev",
  "learn.next": "Next →",
  "learn.practice_10": "Practice these 10",
  "learn.filter.all": "All",
  "learn.filter.beginner": "Beginner",
  "learn.filter.intermediate": "Intermediate",
  "learn.filter.advanced": "Advanced",
  // shared
  "lang.en": "EN",
  "lang.es": "ES",
};

const TABLES: Record<Lang, Record<string, string>> = { en: EN, es: ES };

/** Look up a phrasal UI string. */
export function t(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  return translate(TABLES, lang, key, vars);
}
