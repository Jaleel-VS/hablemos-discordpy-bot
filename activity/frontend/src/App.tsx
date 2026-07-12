import { useEffect, useState } from "react";
import { startSession, type DiscordUser } from "./discord";

type Status =
  | { phase: "loading" }
  | { phase: "ready"; user: DiscordUser }
  | { phase: "error"; message: string };

function avatarUrl(user: DiscordUser): string | null {
  if (!user.avatar) return null;
  return `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png?size=128`;
}

export default function App() {
  const [status, setStatus] = useState<Status>({ phase: "loading" });

  useEffect(() => {
    let cancelled = false;
    startSession()
      .then(({ user }) => {
        if (!cancelled) setStatus({ phase: "ready", user });
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

  const { user } = status;
  const name = user.global_name || user.username;
  const src = avatarUrl(user);

  return (
    <main className="screen">
      <h1>¡Hola, {name}! 👋</h1>
      {src && <img className="avatar" src={src} alt={name} width={96} height={96} />}
      <p className="muted">
        La Activity está funcionando. Pronto podrás jugar al Wordle en español
        aquí.
      </p>
    </main>
  );
}
