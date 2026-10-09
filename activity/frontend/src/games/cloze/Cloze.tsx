import { useCallback, useEffect, useState } from "react";
import type { Lang } from "../../i18n/lang";
import { storedLang } from "../../i18n/lang";
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
import { defaultLangForTarget, DEFAULT_LANG } from "./i18n";

// Screen the player is on within the game. "setup" picks the deck/mode;
// "playing" is the card round; "done" is the score + misses recap.
type Screen = "setup" | "playing" | "done";

export default function Cloze({ accessToken }: GameProps) {
  const [screen, setScreen] = useState<Screen>("setup");
  const [sealed, setSealed] = useState<string | null>(null);
  const [view, setView] = useState<ClozeView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Track the target so the round screen can display lang correctly.
  const [currentTarget, setCurrentTarget] = useState("es");

  // Chrome language: follows target deck when the player never chose explicitly.
  const [lang, setLang] = useState<Lang>(() => storedLang() ?? DEFAULT_LANG);

  // Keep lang in sync with view when the game starts.
  useEffect(() => {
    if (storedLang() === null) {
      setLang(defaultLangForTarget(currentTarget));
    }
  }, [currentTarget]);

  const begin = useCallback(
    async (mode: "daily" | "free", options?: StartOptions) => {
      setBusy(true);
      setError(null);
      try {
        const resp = await startCloze(accessToken, mode, options);
        setSealed(resp.sealed_state);
        setView(resp.view);
        const target = resp.view.target ?? "es";
        setCurrentTarget(target);
        if (storedLang() === null) setLang(defaultLangForTarget(target));
        setScreen(resp.view.status === "over" ? "done" : "playing");
      } catch (e) {
        setError(e instanceof Error ? e.message : "No se pudo iniciar");
      } finally {
        setBusy(false);
      }
    },
    [accessToken],
  );

  const sendAction = useCallback(
    async (guess: string, action: "answer" | "retry" | "skip" | "continue" = "answer", finish = false) => {
      if (!sealed || busy) return;
      setBusy(true);
      setError(null);
      try {
        const resp = await submitCloze(accessToken, sealed, guess, finish, action);
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

  // onAnswer: unified handler for answer/retry/skip/continue actions.
  const answer = useCallback(
    (guess: string, action: "answer" | "retry" | "skip" | "continue" = "answer") => {
      void sendAction(guess, action, false);
    },
    [sendAction],
  );

  // "Terminar" — end the round early and show the recap.
  const finish = useCallback(() => {
    void sendAction("", "answer", true);
  }, [sendAction]);

  // "Practise these N" — start a freeplay round with the missed card ids.
  const practiseMisses = useCallback(
    (ids: string[]) => {
      void begin("free", { target: currentTarget, answer_mode: "type", ids });
    },
    [begin, currentTarget],
  );

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
    return (
      <Summary
        result={view.result}
        lang={lang}
        onReplay={() => setScreen("setup")}
        onPractiseMisses={practiseMisses}
        accessToken={accessToken}
      />
    );
  }

  if (view) {
    return (
      <Round
        view={view}
        lang={lang}
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
