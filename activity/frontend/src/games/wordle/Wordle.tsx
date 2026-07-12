import { useCallback, useEffect, useState } from "react";
import {
  fetchStats,
  startGame,
  submitGuess,
  type GameView,
  type Stats,
} from "../../api";
import Board from "./Board";
import Keyboard from "./Keyboard";

const GAME_KEY = "wordle";

interface WordleProps {
  accessToken: string;
}

type Mode = "daily" | "free";

export default function Wordle({ accessToken }: WordleProps) {
  const [mode, setMode] = useState<Mode>("daily");
  const [sealed, setSealed] = useState<string | null>(null);
  const [view, setView] = useState<GameView | null>(null);
  const [current, setCurrent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);

  const loadStats = useCallback(() => {
    fetchStats(GAME_KEY, accessToken)
      .then(setStats)
      .catch(() => setStats(null));
  }, [accessToken]);

  const newGame = useCallback(
    async (m: Mode) => {
      setBusy(true);
      setError(null);
      setCurrent("");
      try {
        const resp = await startGame(GAME_KEY, accessToken, m);
        setSealed(resp.sealed_state);
        setView(resp.view);
      } catch (e) {
        setError(e instanceof Error ? e.message : "No se pudo iniciar el juego");
      } finally {
        setBusy(false);
      }
    },
    [accessToken],
  );

  useEffect(() => {
    newGame(mode);
    loadStats();
    // Intentionally run on mode change only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  const submit = useCallback(async () => {
    if (!view || !sealed || busy) return;
    if ([...current].length !== view.word_length) {
      setError(`La palabra debe tener ${view.word_length} letras.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await submitGuess(GAME_KEY, accessToken, sealed, current);
      setSealed(resp.sealed_state);
      setView(resp.view);
      setCurrent("");
      if (resp.view.status !== "playing") loadStats();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al enviar");
    } finally {
      setBusy(false);
    }
  }, [view, sealed, busy, current, accessToken, loadStats]);

  const onKey = useCallback(
    (key: string) => {
      if (!view || view.status !== "playing" || busy) return;
      setError(null);
      if (key === "ENTER") {
        void submit();
      } else if (key === "⌫") {
        setCurrent((c) => [...c].slice(0, -1).join(""));
      } else if ([...current].length < view.word_length) {
        setCurrent((c) => c + key);
      }
    },
    [view, busy, current, submit],
  );

  // Physical keyboard support.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Enter") onKey("ENTER");
      else if (e.key === "Backspace") onKey("⌫");
      else if (/^[a-zñ]$/i.test(e.key)) onKey(e.key.toLowerCase());
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onKey]);

  if (!view) {
    return (
      <div className="wordle">
        {error ? <p className="error">{error}</p> : <p className="muted">Cargando…</p>}
      </div>
    );
  }

  const over = view.status !== "playing";
  const result = view.result;

  return (
    <div className="wordle">
      <div className="mode-toggle">
        <button className={mode === "daily" ? "active" : ""} onClick={() => setMode("daily")}>
          Diario{view.puzzle_no ? ` #${view.puzzle_no}` : ""}
        </button>
        <button className={mode === "free" ? "active" : ""} onClick={() => setMode("free")}>
          Libre
        </button>
      </div>

      <Board
        rows={view.rows}
        current={over ? "" : current}
        maxGuesses={view.max_guesses}
        wordLength={view.word_length}
      />

      {error && <p className="error">{error}</p>}

      {over && result && (
        <div className="result">
          <h2>{result.won ? "¡Ganaste! 🎉" : "¡Casi! 😔"}</h2>
          {!result.won && (
            <p className="muted">
              La palabra era <strong>{result.answer.toUpperCase()}</strong>
            </p>
          )}
          <pre className="grid-share">{result.grid}</pre>
          <p className="muted">{result.summary}</p>
          {mode === "free" && (
            <button className="cta" onClick={() => newGame("free")}>
              Jugar otra
            </button>
          )}
        </div>
      )}

      {!over && <Keyboard rows={view.rows} onKey={onKey} disabled={busy} />}

      {stats && stats.games > 0 && (
        <div className="stats">
          <span>{stats.games} jugados</span>
          <span>{Math.round((stats.wins / stats.games) * 100)}% victorias</span>
          <span>🔥 {stats.current_streak}</span>
          <span>máx {stats.max_streak}</span>
        </div>
      )}
    </div>
  );
}
