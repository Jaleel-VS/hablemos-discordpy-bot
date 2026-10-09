import { useEffect, useState } from "react";
import { fetchLeaderboard, type GameInfo, type Leaderboard as Board } from "./api";
import { GAME_REGISTRY } from "./games/registry";

interface LeaderboardProps {
  games: GameInfo[];
  accessToken: string;
  userId: string;
}

type Load = { phase: "loading" } | { phase: "error" } | { phase: "ready"; board: Board };

// Top daily results in this server, one tab per game. Shows the most recent
// daily puzzle anyone here has finished, labelled by its number.
export default function Leaderboard({ games, accessToken, userId }: LeaderboardProps) {
  const [gameKey, setGameKey] = useState(games[0]?.key ?? "");
  const [load, setLoad] = useState<Load>({ phase: "loading" });

  useEffect(() => {
    if (!gameKey) return;
    let cancelled = false;
    setLoad({ phase: "loading" });
    fetchLeaderboard(gameKey, accessToken)
      .then((board) => !cancelled && setLoad({ phase: "ready", board }))
      .catch(() => !cancelled && setLoad({ phase: "error" }));
    return () => {
      cancelled = true;
    };
  }, [gameKey, accessToken]);

  // "HI-SCORES · WORDLE #282"
  const gameDisplay = games.find((g) => g.key === gameKey)?.display_name.toUpperCase() ?? "";
  const puzzleNo = load.phase === "ready" && load.board.puzzle_no != null
    ? ` #${load.board.puzzle_no}`
    : "";
  const title = `HI-SCORES · ${gameDisplay}${puzzleNo}`;

  return (
    <section className="lb" aria-label="Clasificación del servidor">
      <h2 className="lb-title">{title}</h2>
      <div className="lb-tabs" role="tablist">
        {games.map((g) => {
          const meta = GAME_REGISTRY[g.key];
          return (
            <button
              key={g.key}
              role="tab"
              aria-selected={g.key === gameKey}
              className="lb-tab"
              onClick={() => setGameKey(g.key)}
              aria-label={g.display_name}
            >
              {meta?.glyph ?? ""} {g.display_name.toUpperCase()}
            </button>
          );
        })}
      </div>
      {load.phase === "loading" && <p className="muted">Cargando…</p>}
      {load.phase === "error" && <p className="muted">No se pudo cargar la clasificación.</p>}
      {load.phase === "ready" && load.board.entries.length === 0 && (
        <p className="muted">Nadie ha jugado el reto diario todavía.</p>
      )}
      {load.phase === "ready" && load.board.entries.length > 0 && (
        <ol className="lb-list">
          {load.board.entries.map((e) => (
            <li key={e.user_id} className={e.user_id === userId ? "lb-row me" : "lb-row"}>
              <span className="lb-rank">{e.rank}</span>
              <span className="lb-name">{e.name || "Jugador"}</span>
              <span className="lb-score">{e.score}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
