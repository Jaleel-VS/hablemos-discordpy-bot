import { useEffect, useState } from "react";
import { startSession, type Session } from "./discord";
import Wordle from "./games/wordle/Wordle";

type Status =
  | { phase: "loading" }
  | { phase: "ready"; session: Session }
  | { phase: "error"; message: string };

export default function App() {
  const [status, setStatus] = useState<Status>({ phase: "loading" });

  useEffect(() => {
    let cancelled = false;
    startSession()
      .then((session) => {
        if (!cancelled) setStatus({ phase: "ready", session });
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

  const { session } = status;
  const name = session.user.global_name || session.user.username;

  return (
    <main className="app">
      <header className="app-header">
        <span className="app-title">Wordle en español</span>
        <span className="app-user">{name}</span>
      </header>
      <Wordle accessToken={session.accessToken} />
    </main>
  );
}
