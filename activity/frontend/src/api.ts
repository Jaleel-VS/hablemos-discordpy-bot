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
  pronoun: string;
}

export type MatchResult = "exact" | "close" | "wrong";

export interface ConjugationFeedback {
  result: MatchResult;
  expected: string;
  given: string;
  verb: string;
  pronoun: string;
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
}

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
    ...(options ? { options } : {}),
  });
}

export function submitConjugation(
  accessToken: string,
  sealedState: string,
  guess: string,
  finish = false,
): Promise<ConjugationResponse> {
  return post(`/.proxy/api/games/conjugation/guess`, {
    access_token: accessToken,
    sealed_state: sealedState,
    guess,
    finish,
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
