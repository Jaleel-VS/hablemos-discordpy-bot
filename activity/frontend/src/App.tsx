import { useEffect, useState } from "react";
import { listGames, type GameInfo } from "./api";
import { startSession, type Session } from "./discord";
import Home from "./Home";
import { GAME_REGISTRY } from "./games/registry";

type Status =
  | { phase: "loading" }
  | { phase: "ready"; session: Session; games: GameInfo[] }
  | { phase: "error"; message: string };

export default function App() {
  const [status, setStatus] = useState<Status>({ phase: "loading" });
  // Which game is open. null = show the menu. When only one game is
  // registered we skip the menu and open it directly (see effect below).
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Session and game list are independent; fetch together.
    Promise.all([startSession(), listGames()])
      .then(([session, { games }]) => {
        if (cancelled) return;
        const playable = games.filter((g) => GAME_REGISTRY[g.key]);
        setStatus({ phase: "ready", session, games: playable });
        // Single game → open it straight away (no menu friction). This is what
        // lets `$conjuga` / `$wordle` land the player right in the game today,
        // while the menu appears automatically once there are 2+ games.
        if (playable.length === 1) setActive(playable[0].key);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Unknown error";
        setStatus({ phase: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status.phase === "loading") {
    return (
      <main className="screen">
        <p className="muted">Conectando con Discord…</p>
      </main>
    );
  }

  if (status.phase === "error") {
    return (
      <main className="screen">
        <h1>No se pudo conectar</h1>
        <p className="error">{status.message}</p>
        <p className="muted">
          Revisa la configuración de la Activity (URL Mappings y OAuth) y vuelve
          a intentarlo.
        </p>
      </main>
    );
  }

  const { session, games } = status;
  const name = session.user.global_name || session.user.username;
  const single = games.length === 1;
  const meta = active ? GAME_REGISTRY[active] : null;
  const activeInfo = active ? games.find((g) => g.key === active) : null;
  const GameComponent = meta?.component;

  // Back to the menu — only offered when there's more than one game to go back
  // to. With a single game there's nowhere to return, so the game owns the
  // whole surface.
  const onExit = single ? () => {} : () => setActive(null);

  return (
    <main className="app">
      <header className="app-header">
        {GameComponent && !single ? (
          <button className="app-back" onClick={onExit} aria-label="Volver al menú">
            ← Juegos
          </button>
        ) : (
          <span className="app-title">Hablemos</span>
        )}
        <span className="app-user">{name}</span>
      </header>
      {GameComponent && activeInfo ? (
        <GameComponent accessToken={session.accessToken} onExit={onExit} />
      ) : (
        <Home games={games} onPick={setActive} />
      )}
    </main>
  );
}
