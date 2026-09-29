import { useEffect, useState } from "react";
import { fetchLeaderboard, type GameInfo, type Leaderboard as Board } from "./api";

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

  return (
    <section className="board" aria-label="Clasificación del servidor">
      <h2 className="board-title">Clasificación</h2>
      <div className="board-tabs" role="tablist">
        {games.map((g) => (
          <button
            key={g.key}
            role="tab"
            aria-selected={g.key === gameKey}
            className="board-tab"
            onClick={() => setGameKey(g.key)}
          >
            {g.display_name}
          </button>
        ))}
      </div>
      {load.phase === "loading" && <p className="muted">Cargando…</p>}
      {load.phase === "error" && <p className="muted">No se pudo cargar la clasificación.</p>}
      {load.phase === "ready" && load.board.entries.length === 0 && (
        <p className="muted">Nadie ha jugado el reto diario todavía.</p>
      )}
      {load.phase === "ready" && load.board.entries.length > 0 && (
        <>
          <p className="board-puzzle">Reto #{load.board.puzzle_no}</p>
          <ol className="board-list">
            {load.board.entries.map((e) => (
              <li key={e.user_id} className={e.user_id === userId ? "board-row me" : "board-row"}>
                <span className="board-rank">{e.rank}</span>
                <span className="board-name">{e.name || "Jugador"}</span>
                <span className="board-score">{e.score}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
