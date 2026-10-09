// Wordle UI strings. Language preference is shared (src/i18n/lang.tsx);
// this file owns only the string tables.
import { type Lang, translate } from "../../i18n/lang";

export type { Lang };

/** Wordle's audience is English speakers learning Spanish. */
export const DEFAULT_LANG: Lang = "en";

const EN: Record<string, string> = {
  // mode labels
  "mode.daily": "Daily",
  "mode.free": "Free play",
  // status / result
  "result.win": "You got it!",
  "result.loss": "Not this time",
  "result.answer_was": "The word was",
  "result.play_again": "Play another",
  // errors (matched to the two Spanish backend messages)
  "error.bad_length": "Word must be {n} letters.",
  "error.not_in_list": "Not in word list.",
  // accent rule (W2)
  "accent_rule": "Accents don't count (árbol = arbol) — but ñ is its own letter.",
  // learning card (W1)
  "card.pos.noun": "noun",
  "card.pos.verb": "verb",
  "card.pos.adjective": "adjective",
  "card.pos.adverb": "adverb",
  "card.pos.other": "word",
  "card.form_label": "Form",
  "card.example_label": "Example",
  // hint (W4)
  "hint.label": "Hint",
  // stats
  "stats.played": "played",
  "stats.wins": "wins",
  "stats.streak": "streak",
  "stats.max": "best",
  // loading
  "loading": "Loading…",
  "error.start": "Couldn't start game",
  "error.submit": "Error submitting",
  // lang toggle
  "lang.en": "EN",
  "lang.es": "ES",
  // aria labels
  "key.enter": "Submit word",
  "key.delete": "Delete letter",
};

const ES: Record<string, string> = {
  "mode.daily": "Diario",
  "mode.free": "Libre",
  "result.win": "¡Ganaste!",
  "result.loss": "Esta vez no",
  "result.answer_was": "La palabra era",
  "result.play_again": "Jugar otra",
  "error.bad_length": "La palabra debe tener {n} letras.",
  "error.not_in_list": "Esa palabra no está en la lista.",
  "accent_rule": "Los acentos no cuentan (árbol = arbol) — pero la ñ es su propia letra.",
  "card.pos.noun": "sustantivo",
  "card.pos.verb": "verbo",
  "card.pos.adjective": "adjetivo",
  "card.pos.adverb": "adverbio",
  "card.pos.other": "palabra",
  "card.form_label": "Forma",
  "card.example_label": "Ejemplo",
  "hint.label": "Pista",
  "stats.played": "jugados",
  "stats.wins": "victorias",
  "stats.streak": "racha",
  "stats.max": "máx",
  "loading": "Cargando…",
  "error.start": "No se pudo iniciar el juego",
  "error.submit": "Error al enviar",
  "lang.en": "EN",
  "lang.es": "ES",
  "key.enter": "Enviar palabra",
  "key.delete": "Borrar letra",
};

const TABLES: Record<Lang, Record<string, string>> = { en: EN, es: ES };

/** Look up a Wordle UI string. */
export function t(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  return translate(TABLES, lang, key, vars);
}
