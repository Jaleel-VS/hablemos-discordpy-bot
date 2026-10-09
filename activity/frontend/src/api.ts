// Typed client for the games API. Every call goes through the /.proxy prefix
// so it survives Discord's CSP-restricted proxy.
export type Tile = "green" | "yellow" | "gray";

export interface Row {
  guess: string;
  tiles: Tile[];
}

export interface ResultPayload {
  won: boolean;
  mode: string;
  puzzle_no: number | null;
  guesses_used: number;
  max_guesses: number;
  score: string;
  grid: string;
  summary: string;
  answer: string;
}

// ── wordle game ───────────────────────────────────────────────────────────────
export interface WordleLearningCard {
  display: string;
  pos: "noun" | "verb" | "adjective" | "adverb" | "other";
  en: string;
  example_es: string;
  example_en: string;
  lemma: string;
  form: string;
}

export interface WordleHint {
  pos: string;
  en: string;
}

export interface WordleResultPayload extends ResultPayload {
  learning_card?: WordleLearningCard;
}

export interface WordleView extends GameView {
  result?: WordleResultPayload;
  hint?: WordleHint;
}

export interface GameView {
  game: string;
  mode: "daily" | "free";
  max_guesses: number;
  word_length: number;
  puzzle_no: number | null;
  rows: Row[];
  status: "playing" | "won" | "lost";
  result?: ResultPayload;
}

export interface GameResponse {
  sealed_state: string;
  view: GameView;
}

export interface Stats {
  games: number;
  wins: number;
  current_streak: number;
  max_streak: number;
  distribution: Record<string, number>;
}

// ── game registry ───────────────────────────────────────────────────────────
export interface GameInfo {
  key: string;
  display_name: string;
}

// ── conjugation game ──────────────────────────────────────────────────────────
export interface ConjugationPrompt {
  verb: string;
  english: string;
  tense: string;
  tense_label: string;
  tense_english: string;
  pronoun: string;
  pronoun_english: string;
}

export type MatchResult = "exact" | "close" | "wrong" | "skipped";

export interface ConjugationFeedback {
  result: MatchResult;
  // Withheld during the daily sprint (a fixed shared sequence) so answers
  // can't be harvested mid-run; present in freeplay/practice and in the recap.
  expected?: string;
  given: string;
  verb: string;
  // True when this feedback is the retype after a reveal (untimed practice);
  // it did not score, so the UI acknowledges rather than celebrates.
  retry?: boolean;
  pronoun: string;
  tense: string;
  // Present in free mode only (withheld in daily anti-harvest).
  note?: string;
  row?: Record<string, string>;
}

export interface ConjugationMiss {
  verb: string;
  tense: string;
  pronoun: string;
  expected: string;
  given: string;
  result: MatchResult;
}

export interface ConjugationResult {
  won: boolean;
  mode: string;
  puzzle_no: number | null;
  correct: number;
  total: number;
  best_streak: number;
  score: string;
  grid: string;
  summary: string;
  misses: ConjugationMiss[];
  skipped: number;
  close: number;
  strict: boolean;
  breakdown: {
    tenses: Record<string, { correct: number; total: number }>;
    pronouns: Record<string, { correct: number; total: number }>;
  };
  review_verbs: string[];
}

export interface ConjugationView {
  game: "conjugation";
  mode: "daily" | "free";
  timed: boolean;
  duration: number | null; // null when untimed
  deadline: string | null; // ISO server-authoritative end time; null when untimed
  puzzle_no: number | null;
  correct: number;
  streak: number;
  best_streak: number;
  answered_count: number;
  status: "playing" | "over";
  last: ConjugationFeedback | null;
  prompt?: ConjugationPrompt;
  result?: ConjugationResult;
  awaiting_retry: boolean;
  strict: boolean;
  items: number;          // 0 = open-ended
  remaining_items: number | null;
}

export interface ConjugationResponse {
  sealed_state: string;
  view: ConjugationView;
}

// Options a game may take at start (conjugation: verb set / tenses / pronouns /
// whether the run is the 60s sprint or untimed practice).
export interface StartOptions {
  set?: string;
  tenses?: string[];
  pronouns?: string[];
  timed?: boolean;
  // Conjugation: strict accent grading, show variant pronouns, item count cap,
  // review-mode verb override.
  strict?: boolean;
  variants?: boolean;
  items?: number;
  verbs?: string[];
  // Cloze: target language (which word is blanked), difficulty, and answer mode.
  target?: string;
  difficulty?: string;
  answer_mode?: "choice" | "type";
  // Phrasal: which part of the phrasal verb to blank; review-mode id override.
  blank_mode?: "particle" | "whole";
  ids?: string[];
}

// ── conjugation catalog ───────────────────────────────────────────────────────
export interface ConjugationTenseInfo {
  key: string;
  label: string;
  english: string;
  hint: string;
  example: string;
}

export interface ConjugationPronounInfo {
  key: string;
  english: string;
}

export interface ConjugationSetInfo {
  key: string;
  label: string;
  size: number;
}

export interface ConjugationCatalog {
  tenses: ConjugationTenseInfo[];
  pronouns: ConjugationPronounInfo[];
  sets: ConjugationSetInfo[];
  daily_tenses: string[];
}

// ── cloze game ────────────────────────────────────────────────────────────────
export interface ClozePrompt {
  target: string; // language of the blanked word ("es" | "en")
  cloze: string; // sentence with a single ___ blank
  context: string; // full sentence in the OTHER language
  difficulty: string;
  options?: string[]; // 4 shuffled options (choice mode only; omitted in type mode)
}


export interface ClozeFeedback {
  result: MatchResult;
  // Withheld during the daily round (a fixed shared sequence) so answers can't
  // be harvested mid-run; present in freeplay and in the recap.
  answer?: string;
  given: string;
  context: string;
  // Freeplay only: the completed sentence (blank filled in) for the miss reveal.
  sentence?: string;
  // True when this feedback is from a retry, not a fresh scored answer.
  retry?: boolean;
}


export interface ClozeMiss {
  id: string;
  answer: string;
  given: string;
  result: MatchResult;
  // Completed sentence + translation for the recap reveal.
  sentence?: string;
  context?: string;
}
export interface ClozeResult {
  won: boolean;
  mode: string;
  puzzle_no: number | null;
  target: string;
  answer_mode: "choice" | "type";
  correct: number;
  total: number;
  best_streak: number;
  score: string;
  grid: string;
  summary: string;
  misses: ClozeMiss[];
  // Ids of wrong+close cards (max 10) for the "Practise these N" CTA.
  review_ids: string[];
}


export interface ClozeView {
  game: "cloze";
  mode: "daily" | "free";
  answer_mode: "choice" | "type";
  target: string;
  difficulty: string | null;
  puzzle_no: number | null;
  round_size: number;
  seq: number;
  // Withheld (null) during daily play so a replayed token can't probe the
  // answer via which option bumps the score; present in freeplay and once the
  // daily round is over.
  correct: number | null;
  streak: number | null;
  best_streak: number | null;
  answered_count: number;
  status: "playing" | "over";
  // Type mode (freeplay): same card stays; client must retype, or send skip.
  awaiting_retry: boolean;
  // Choice mode (freeplay): reveal card shown; client sends action="continue".
  awaiting_continue: boolean;
  last: ClozeFeedback | null;
  prompt?: ClozePrompt;
  result?: ClozeResult;
}


export interface ClozeResponse {
  sealed_state: string;
  view: ClozeView;
}

// The server (guild) the Activity was launched in, set once after the SDK
// handshake. Sent with every game start so finished results are attributed to
// it for the server leaderboard. null in DMs.
let guildId: string | null = null;

export function setGuildId(id: string | null): void {
  guildId = id;
}

const guildField = () => (guildId ? { guild_id: guildId } : {});

async function post<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    // Surface the backend's friendly (Spanish) detail message when present.
    let detail = `Error ${resp.status}`;
    try {
      const data = await resp.json();
      if (data?.detail) detail = data.detail;
    } catch {
      /* ignore parse failure, keep generic */
    }
    throw new Error(detail);
  }
  return (await resp.json()) as T;
}

export function listGames(): Promise<{ games: GameInfo[] }> {
  return fetch("/.proxy/api/games").then((r) => {
    if (!r.ok) throw new Error(`Error ${r.status}`);
    return r.json() as Promise<{ games: GameInfo[] }>;
  });
}

export function startGame(
  gameKey: string,
  accessToken: string,
  mode: "daily" | "free",
  options?: StartOptions,
): Promise<GameResponse> {
  return post(`/.proxy/api/games/${gameKey}/start`, {
    access_token: accessToken,
    mode,
    ...guildField(),
    ...(options ? { options } : {}),
  });
}

// Conjugation shares the generic start/guess endpoints but returns its own view
// shape, so it gets typed wrappers rather than reusing the Wordle GameResponse.
export function startConjugation(
  accessToken: string,
  mode: "daily" | "free",
  options?: StartOptions,
): Promise<ConjugationResponse> {
  return post(`/.proxy/api/games/conjugation/start`, {
    access_token: accessToken,
    mode,
    ...guildField(),
    ...(options ? { options } : {}),
  });
}

export function submitConjugation(
  accessToken: string,
  sealedState: string,
  guess: string,
  finish = false,
  action: "answer" | "skip" | "retry" = "answer",
): Promise<ConjugationResponse> {
  return post(`/.proxy/api/games/conjugation/guess`, {
    access_token: accessToken,
    sealed_state: sealedState,
    guess,
    finish,
    action,
  });
}

export function fetchConjugationCatalog(): Promise<ConjugationCatalog> {
  return fetch("/.proxy/api/games/conjugation/catalog").then((r) => {
    if (!r.ok) throw new Error(`Error ${r.status}`);
    return r.json() as Promise<ConjugationCatalog>;
  });
}

export function submitGuess(
  gameKey: string,
  accessToken: string,
  sealedState: string,
  guess: string,
): Promise<GameResponse> {
  return post(`/.proxy/api/games/${gameKey}/guess`, {
    access_token: accessToken,
    sealed_state: sealedState,
    guess,
  });
}

export function fetchStats(gameKey: string, accessToken: string): Promise<Stats> {
  return post(`/.proxy/api/games/${gameKey}/stats`, { access_token: accessToken });
}

export interface LeaderboardEntry {
  rank: number;
  user_id: string; // string: snowflakes exceed Number.MAX_SAFE_INTEGER
  name: string;
  score: string;
}

export interface Leaderboard {
  puzzle_no: number | null; // null when nobody in the server has played yet
  entries: LeaderboardEntry[];
}

export function fetchLeaderboard(gameKey: string, accessToken: string): Promise<Leaderboard> {
  return post(`/.proxy/api/games/${gameKey}/leaderboard`, {
    access_token: accessToken,
    ...guildField(),
  });
}

// Cloze shares the generic start/guess endpoints but returns its own view
// shape, so it gets typed wrappers (like conjugation).
export function startCloze(
  accessToken: string,
  mode: "daily" | "free",
  options?: StartOptions,
): Promise<ClozeResponse> {
  return post(`/.proxy/api/games/cloze/start`, {
    access_token: accessToken,
    mode,
    ...guildField(),
    ...(options ? { options } : {}),
  });
}

export function submitCloze(
  accessToken: string,
  sealedState: string,
  guess: string,
  finish = false,
  action: "answer" | "retry" | "skip" | "continue" = "answer",
): Promise<ClozeResponse> {
  return post(`/.proxy/api/games/cloze/guess`, {
    access_token: accessToken,
    sealed_state: sealedState,
    guess,
    finish,
    action,
  });
}


// ── phrasal-verb game ─────────────────────────────────────────────────────────
export interface PhrasalPrompt {
  // id intentionally absent: never in the in-play prompt view (security invariant).
  blank_mode: "particle" | "whole";
  example: string; // sentence with a single ___ blank
  // gloss_es is the primary meaning anchor; first EN definition is behind disclosure.
  gloss_es: string | null;
  definitions: string[]; // all EN senses
  difficulty: string;
  base: string | null; // shown in particle mode (the verb whose particle is hidden)
  // Particle mode: the inflected verb is already written into `example`
  // ("signing ___"), so the "(sign)" prefix hint is redundant.
  base_inline?: boolean;
  options?: string[]; // present only in choice mode
}

export interface PhrasalFeedback {
  result: MatchResult;
  answer?: string;   // withheld during daily play
  verb?: string;
  given: string;
  gloss_es?: string | null;
  sentence?: string; // example with answer filled in (freeplay miss reveal)
  definitions?: string[];
  retry?: boolean;   // true if this is a retype confirmation, not a new answer
  // The full inflected span the sentence's blank stands for ("signing over");
  // the reveal highlights this so particle mode reads as real English.
  span?: string;
}

export interface PhrasalMiss {
  id: string;
  verb: string;
  answer: string;
  given: string;
  result: MatchResult;
  gloss_es?: string | null;
  sentence?: string; // example with answer filled in (shown in recap)
  span?: string; // full inflected span to highlight in `sentence`
}

export interface PhrasalResult {
  won: boolean;
  mode: string;
  puzzle_no: number | null;
  blank_mode: "particle" | "whole";
  answer_mode: "choice" | "type";
  correct: number;
  total: number;
  best_streak: number;
  score: string;
  grid: string;
  summary: string;
  misses: PhrasalMiss[];
  review_ids: string[]; // wrong+close ids, validated, capped 10, daily ids excluded
}

export interface PhrasalView {
  game: "phrasal";
  mode: "daily" | "free";
  answer_mode: "choice" | "type";
  blank_mode: "particle" | "whole";
  difficulty: string | null;
  puzzle_no: number | null;
  round_size: number;
  seq: number;
  // Withheld (null) during daily play so a replayed token can't probe the
  // answer via which option bumps the score; present in freeplay and once over.
  correct: number | null;
  streak: number | null;
  best_streak: number | null;
  answered_count: number;
  status: "playing" | "over";
  awaiting_retry: boolean;
  awaiting_continue: boolean;
  last: PhrasalFeedback | null;
  prompt?: PhrasalPrompt;
  result?: PhrasalResult;
}

export interface PhrasalResponse {
  sealed_state: string;
  view: PhrasalView;
}

export function startPhrasal(
  accessToken: string,
  mode: "daily" | "free",
  options?: StartOptions,
): Promise<PhrasalResponse> {
  return post(`/.proxy/api/games/phrasal/start`, {
    access_token: accessToken,
    mode,
    ...guildField(),
    ...(options ? { options } : {}),
  });
}

export function submitPhrasal(
  accessToken: string,
  sealedState: string,
  guess: string,
  finish = false,
  action: "answer" | "retry" | "continue" = "answer",
): Promise<PhrasalResponse> {
  return post(`/.proxy/api/games/phrasal/guess`, {
    access_token: accessToken,
    sealed_state: sealedState,
    guess,
    finish,
    action,
  });
}

// The Learn ("Aprender") deck is read-only vocabulary (no game state), so it's
// a plain GET outside the game-engine endpoints.
export interface PhrasalDeckEntry {
  id: string;
  verb: string;
  particle: string;
  base: string;
  definitions: string[];
  gloss_es: string | null;
  example: string; // shown UNBLANKED (the verb in a real sentence)
  difficulty: string;
}

export interface PhrasalDeck {
  difficulties: Record<string, string>;
  verbs: PhrasalDeckEntry[];
}

export function fetchPhrasalDeck(difficulty?: string): Promise<PhrasalDeck> {
  const q = difficulty ? `?difficulty=${encodeURIComponent(difficulty)}` : "";
  return fetch(`/.proxy/api/games/phrasal/deck${q}`).then((r) => {
    if (!r.ok) throw new Error(`Error ${r.status}`);
    return r.json() as Promise<PhrasalDeck>;
  });
}

// ── pet ───────────────────────────────────────────────────────────────────────

export interface PetProfile {
  species: string;
  color: string;
  name: string;
}

export type PetMood = "idle" | "sleepy" | "waiting" | "happy";

export interface PetState {
  /** Always present: a default derived from the user id until customised. */
  pet: PetProfile;
  mood: PetMood;
  streak_days: number;
  played_today: boolean;
  games_this_week: number;
  favorite_game: string | null;
}

export interface PetChoice {
  species: string;
  color: string;
  name?: string;
}

export function fetchPet(accessToken: string): Promise<PetState> {
  return post("/.proxy/api/pet/me", { access_token: accessToken });
}

export function choosePet(accessToken: string, choice: PetChoice): Promise<PetState> {
  return post("/.proxy/api/pet/choose", {
    access_token: accessToken,
    species: choice.species,
    color: choice.color,
    name: choice.name,
  });
}
