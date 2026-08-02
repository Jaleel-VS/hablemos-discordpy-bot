import { useCallback, useEffect, useState } from "react";
import {
  startCloze,
  submitCloze,
  type ClozeView,
  type StartOptions,
} from "../../api";
import type { GameProps } from "../registry";
import Setup from "./Setup";
import Round from "./Round";
import Summary from "./Summary";

// Screen the player is on within the game. "setup" picks the deck/mode;
// "playing" is the card round; "done" is the score + misses recap.
type Screen = "setup" | "playing" | "done";

export default function Cloze({ accessToken }: GameProps) {
  const [screen, setScreen] = useState<Screen>("setup");
  const [sealed, setSealed] = useState<string | null>(null);
  const [view, setView] = useState<ClozeView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const begin = useCallback(
    async (mode: "daily" | "free", options?: StartOptions) => {
      setBusy(true);
      setError(null);
      try {
        const resp = await startCloze(accessToken, mode, options);
        setSealed(resp.sealed_state);
        setView(resp.view);
        setScreen(resp.view.status === "over" ? "done" : "playing");
      } catch (e) {
        setError(e instanceof Error ? e.message : "No se pudo iniciar");
      } finally {
        setBusy(false);
      }
    },
    [accessToken],
  );

  const answer = useCallback(
    async (guess: string, finish = false) => {
      if (!sealed || busy) return;
      setBusy(true);
      setError(null);
      try {
        const resp = await submitCloze(accessToken, sealed, guess, finish);
        setSealed(resp.sealed_state);
        setView(resp.view);
        if (resp.view.status === "over") setScreen("done");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al enviar");
      } finally {
        setBusy(false);
      }
    },
    [accessToken, sealed, busy],
  );

  // "Terminar" — end the round early and show the recap.
  const finish = useCallback(() => {
    void answer("", true);
  }, [answer]);

  // Auto-dismiss the round error toast so it doesn't linger.
  useEffect(() => {
    if (!error || screen !== "playing") return;
    const id = window.setTimeout(() => setError(null), 1800);
    return () => window.clearTimeout(id);
  }, [error, screen]);

  if (screen === "setup") {
    return <Setup onStart={begin} busy={busy} error={error} />;
  }

  if (screen === "done" && view?.result) {
    return <Summary result={view.result} onReplay={() => setScreen("setup")} />;
  }

  if (view) {
    return (
      <Round
        view={view}
        busy={busy}
        error={error}
        onAnswer={answer}
        onFinish={finish}
      />
    );
  }

  return (
    <div className="cloze">
      <p className="muted">Cargando…</p>
    </div>
  );
}
