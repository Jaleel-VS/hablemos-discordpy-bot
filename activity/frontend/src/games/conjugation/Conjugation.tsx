import { useCallback, useRef, useState } from "react";
import {
  startConjugation,
  submitConjugation,
  type ConjugationView,
  type StartOptions,
} from "../../api";
import type { GameProps } from "../registry";
import Setup from "./Setup";
import Sprint from "./Sprint";
import Summary from "./Summary";

// Screen the player is on within the game. "setup" picks the drill; "playing"
// is the timed sprint; "done" is the score + misses recap.
type Screen = "setup" | "playing" | "done";

export default function Conjugation({ accessToken }: GameProps) {
  const [screen, setScreen] = useState<Screen>("setup");
  const [sealed, setSealed] = useState<string | null>(null);
  const [view, setView] = useState<ConjugationView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Guards against a late submit response flipping us back after the game ends.
  const overRef = useRef(false);

  const begin = useCallback(
    async (mode: "daily" | "free", options?: StartOptions) => {
      setBusy(true);
      setError(null);
      overRef.current = false;
      try {
        const resp = await startConjugation(accessToken, mode, options);
        setSealed(resp.sealed_state);
        setView(resp.view);
        setScreen("playing");
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
      if (!sealed || busy || overRef.current) return;
      setBusy(true);
      // TEMP measurement (remove after the snappiness investigation): wall-clock
      // from submit to response as felt by the client. Compare against the
      // server's total_ms log line — the gap is pure network/proxy latency.
      const t0 = performance.now();
      try {
        const resp = await submitConjugation(accessToken, sealed, guess, finish);
        console.info(`[conj] submit round-trip: ${(performance.now() - t0).toFixed(0)}ms`);
        setSealed(resp.sealed_state);
        setView(resp.view);
        if (resp.view.status === "over") {
          overRef.current = true;
          setScreen("done");
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al enviar");
      } finally {
        setBusy(false);
      }
    },
    [accessToken, sealed, busy],
  );

  // "Terminar" in untimed practice — end the run and show the recap.
  const finish = useCallback(() => {
    if (overRef.current) return;
    void answer("", true);
  }, [answer]);

  // When the client-side countdown hits zero, end the run via the finish
  // action — NOT a normal empty guess. The finish path finalizes without
  // grading, so the unanswered prompt on screen at the buzzer is not counted
  // wrong. (Sending guess="" would grade it as a wrong answer.)
  const flushTimeout = useCallback(() => {
    if (overRef.current) return;
    void answer("", true);
  }, [answer]);

  if (screen === "setup") {
    return <Setup onStart={begin} busy={busy} error={error} />;
  }

  if (screen === "done" && view?.result) {
    return (
      <Summary
        result={view.result}
        onReplay={() => setScreen("setup")}
      />
    );
  }

  if (view) {
    return (
      <Sprint
        view={view}
        busy={busy}
        onAnswer={answer}
        onTimeout={flushTimeout}
        onFinish={finish}
      />
    );
  }

  return (
    <div className="conj">
      <p className="muted">Cargando…</p>
    </div>
  );
}
