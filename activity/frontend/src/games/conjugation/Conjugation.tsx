import { useCallback, useEffect, useRef, useState } from "react";
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
  // Set when the timer hits zero while a normal answer is still in flight. The
  // flush can't run then (answer() is busy), so we remember it and fire it once
  // the in-flight request settles — otherwise the buzzer flush is dropped and
  // the game hangs at 0s.
  const pendingFlushRef = useRef(false);

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
      setError(null); // clear any prior submit-error toast
      try {
        let resp = await submitConjugation(accessToken, sealed, guess, finish);
        // If the buzzer fired while this answer was in flight, finalize now —
        // using THIS response's fresh sealed state (not the stale closure), so
        // the answer we just graded is preserved before the game ends.
        if (pendingFlushRef.current && resp.view.status === "playing") {
          pendingFlushRef.current = false;
          resp = await submitConjugation(accessToken, resp.sealed_state, "", true);
        }
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

  // Auto-dismiss the sprint error toast so it doesn't linger. The Setup error
  // is a form-validation state we leave until the next action.
  useEffect(() => {
    if (!error || screen !== "playing") return;
    const id = window.setTimeout(() => setError(null), 1800);
    return () => window.clearTimeout(id);
  }, [error, screen]);

  // When the client-side countdown hits zero, end the run via the finish
  // action — NOT a normal empty guess. The finish path finalizes without
  // grading, so the unanswered prompt on screen at the buzzer is not counted
  // wrong. (Sending guess="" would grade it as a wrong answer.)
  //
  // If an answer is mid-flight (busy), answer() would no-op and drop the
  // flush, hanging the game at 0s — so defer it and let answer()'s finally
  // fire it once that request settles.
  const flushTimeout = useCallback(() => {
    if (overRef.current) return;
    if (busy) {
      pendingFlushRef.current = true;
      return;
    }
    void answer("", true);
  }, [answer, busy]);

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
        error={error}
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
