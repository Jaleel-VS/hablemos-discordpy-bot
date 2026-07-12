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

export function startGame(
  gameKey: string,
  accessToken: string,
  mode: "daily" | "free",
): Promise<GameResponse> {
  return post(`/.proxy/api/games/${gameKey}/start`, { access_token: accessToken, mode });
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
