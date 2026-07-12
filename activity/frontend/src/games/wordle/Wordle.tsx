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
  // Row index to flip-reveal after a successful guess; cleared once played.
  const [revealRow, setRevealRow] = useState<number | null>(null);
  const [shake, setShake] = useState(false);

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
      setRevealRow(null);
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

  const triggerShake = useCallback(() => {
    setShake(true);
    window.setTimeout(() => setShake(false), 420);
  }, []);

  const submit = useCallback(async () => {
    if (!view || !sealed || busy) return;
    if ([...current].length !== view.word_length) {
      setError(`La palabra debe tener ${view.word_length} letras.`);
      triggerShake();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await submitGuess(GAME_KEY, accessToken, sealed, current);
      setSealed(resp.sealed_state);
      // Flip-reveal the row that was just added (the last one).
      setRevealRow(resp.view.rows.length - 1);
      setView(resp.view);
      setCurrent("");
      if (resp.view.status !== "playing") loadStats();
    } catch (e) {
      // Backend rejected the guess (not a word, wrong length): shake the row.
      setError(e instanceof Error ? e.message : "Error al enviar");
      triggerShake();
    } finally {
      setBusy(false);
    }
  }, [view, sealed, busy, current, accessToken, loadStats, triggerShake]);

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
        revealRow={revealRow}
        shake={shake}
      />

      {error && !over && <p className="error">{error}</p>}

      {over && result ? (
        <div className="result">
          <h2>{result.won ? "¡Ganaste!" : "¡Casi!"}</h2>
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
      ) : (
        <Keyboard rows={view.rows} onKey={onKey} disabled={busy} />
      )}

      {stats && stats.games > 0 && (
        <div className="stats">
          <span><strong>{stats.games}</strong> jugados</span>
          <span><strong>{Math.round((stats.wins / stats.games) * 100)}%</strong> victorias</span>
          <span>🔥 <strong>{stats.current_streak}</strong></span>
          <span>máx <strong>{stats.max_streak}</strong></span>
        </div>
      )}
    </div>
  );
}
