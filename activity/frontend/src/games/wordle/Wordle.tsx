import { useCallback, useEffect, useState } from "react";
import PetReaction from "../../pet/PetReaction";
import {
  fetchStats,
  startGame,
  submitGuess,
  type Stats,
  type WordleView,
  type WordleLearningCard,
} from "../../api";
import type { GameProps } from "../registry";
import { LangToggle, useLang, type Lang } from "../../i18n/lang";
import { t, DEFAULT_LANG } from "./i18n";
import Board from "./Board";
import Keyboard from "./Keyboard";
import "../../styles/wordle.css";

const GAME_KEY = "wordle";

type Mode = "daily" | "free";

// Maps backend Spanish error messages to i18n keys for bilingual display (W3).
const ERROR_MAP: Record<string, string> = {
  "La palabra debe tener": "error.bad_length",
  "Esa palabra no está en la lista": "error.not_in_list",
};

function mapError(raw: string, lang: Lang, wordLength: number): string {
  for (const [fragment, key] of Object.entries(ERROR_MAP)) {
    if (raw.includes(fragment)) return t(lang, key, { n: wordLength });
  }
  return raw;
}

interface LearningCardProps {
  card: WordleLearningCard;
  lang: Lang;
}

function LearningCard({ card, lang }: LearningCardProps) {
  const posLabel = t(lang, `card.pos.${card.pos}`);
  // Highlight the display word inside example_es (case-insensitive).
  const parts = card.example_es.split(new RegExp(`(${card.display})`, "i"));

  return (
    <div className="wordle-learning-card reveal-card">
      <div className="wlc-word">{card.display.toUpperCase()}</div>
      <div className="wlc-gloss">
        <span className="wlc-pos">{posLabel}</span>
        <span className="wlc-sep"> · </span>
        <span className="wlc-en">{card.en}</span>
      </div>
      {card.form && (
        <div className="wlc-form">
          <span className="wlc-form-label">{t(lang, "card.form_label")}: </span>
          {card.form}
        </div>
      )}
      <div className="wlc-example">
        <span className="wlc-example-label">{t(lang, "card.example_label")}: </span>
        {parts.map((part, i) =>
          part.toLowerCase() === card.display.toLowerCase()
            ? <em key={i} className="wlc-highlight">{part}</em>
            : <span key={i}>{part}</span>
        )}
      </div>
      <div className="wlc-example-en">{card.example_en}</div>
    </div>
  );
}

export default function Wordle({ accessToken }: GameProps) {
  const [lang, setLang] = useLang(DEFAULT_LANG);
  const [mode, setMode] = useState<Mode>("daily");
  const [sealed, setSealed] = useState<string | null>(null);
  const [view, setView] = useState<WordleView | null>(null);
  const [current, setCurrent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
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
      try {
        const resp = await startGame(GAME_KEY, accessToken, m);
        setSealed(resp.sealed_state);
        setView(resp.view as WordleView);
        setMode(m);
        setCurrent("");
        setRevealRow(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : t(lang, "error.start"));
      } finally {
        setBusy(false);
      }
    },
    [accessToken, lang],
  );

  useEffect(() => {
    void newGame(mode);
    loadStats();
    // Run on mount only; later mode switches go through newGame explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const triggerShake = useCallback(() => {
    setShake(true);
    window.setTimeout(() => setShake(false), 420);
  }, []);

  const submit = useCallback(async () => {
    if (!view || !sealed || busy) return;
    if ([...current].length !== view.word_length) {
      setError(t(lang, "error.bad_length", { n: view.word_length }));
      triggerShake();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await submitGuess(GAME_KEY, accessToken, sealed, current);
      setSealed(resp.sealed_state);
      setRevealRow(resp.view.rows.length - 1);
      setView(resp.view as WordleView);
      setCurrent("");
      if (resp.view.status !== "playing") loadStats();
    } catch (e) {
      const raw = e instanceof Error ? e.message : t(lang, "error.submit");
      setError(mapError(raw, lang, view.word_length));
      triggerShake();
    } finally {
      setBusy(false);
    }
  }, [view, sealed, busy, current, accessToken, lang, loadStats, triggerShake]);

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

  // Physical keyboard — W3: ignore events from input/textarea/contenteditable.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable
      )
        return;
      if (e.key === "Enter") onKey("ENTER");
      else if (e.key === "Backspace") onKey("⌫");
      else if (/^[a-zñ]$/i.test(e.key)) onKey(e.key.toLowerCase());
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onKey]);

  // Auto-dismiss toast after 1.8 s.
  useEffect(() => {
    if (!error) return;
    const id = window.setTimeout(() => setError(null), 1800);
    return () => window.clearTimeout(id);
  }, [error]);

  if (!view) {
    return (
      <div className="wordle">
        {error ? <p className="error">{error}</p> : <p className="muted">{t(lang, "loading")}</p>}
      </div>
    );
  }

  const over = view.status !== "playing";
  const result = view.result;

  return (
    <div className="wordle">
      <div className="wordle-top">
        <div className="mode-toggle">
          <button
            className={mode === "daily" ? "active" : ""}
            onClick={() => { if (mode !== "daily") void newGame("daily"); }}
          >
            {t(lang, "mode.daily")}
            {view.puzzle_no != null && view.mode === "daily" ? ` #${view.puzzle_no}` : ""}
          </button>
          <button
            className={mode === "free" ? "active" : ""}
            onClick={() => { if (mode !== "free") void newGame("free"); }}
          >
            {t(lang, "mode.free")}
          </button>
        </div>
        <LangToggle lang={lang} onChange={setLang} />
      </div>

      {/* W2: accent rule one-liner (only while playing; the card teaches after) */}
      {!over && <p className="wordle-accent-rule">{t(lang, "accent_rule")}</p>}

      <Board
        rows={view.rows}
        current={over ? "" : current}
        maxGuesses={view.max_guesses}
        wordLength={view.word_length}
        revealRow={revealRow}
        shake={shake}
      />

      {/* W4: freeplay hint after 3 misses, derived at view time */}
      {!over && view.hint && (
        <p className="wordle-hint">
          <span className="wordle-hint-label">{t(lang, "hint.label")}: </span>
          {view.hint.pos} · {view.hint.en}
        </p>
      )}

      <div className="toast-anchor">
        {error && (
          <div className="toast" role="status" key={error}>
            {error}
          </div>
        )}
      </div>

      {over && result ? (
        <div className="result">
          <div className="pet-reaction-slot">
            <PetReaction accessToken={accessToken} outcome={result.won ? "win" : "meh"} />
          </div>
          <h2>{result.won ? t(lang, "result.win") : t(lang, "result.loss")}</h2>
          {/* The board above already shows the game; the share grid is for the
              channel post, so the end screen spends its space on the word. */}
          <p className="muted">{result.summary}</p>

          {/* W1: learning card on win and loss — it names the word, so a loss
              needs no separate "the word was" line. */}
          {result.learning_card ? (
            <LearningCard card={result.learning_card} lang={lang} />
          ) : (
            !result.won && (
              <p className="muted">
                {t(lang, "result.answer_was")} <strong>{result.answer.toUpperCase()}</strong>
              </p>
            )
          )}

          {view.mode === "free" && (
            <button className="cta" onClick={() => void newGame("free")}>
              {t(lang, "result.play_again")}
            </button>
          )}
        </div>
      ) : (
        <Keyboard rows={view.rows} onKey={onKey} disabled={busy} lang={lang} />
      )}

      {stats && stats.games > 0 && (
        <div className="stats">
          <span><strong>{stats.games}</strong> {t(lang, "stats.played")}</span>
          <span><strong>{Math.round((stats.wins / stats.games) * 100)}%</strong> {t(lang, "stats.wins")}</span>
          <span>🔥 <strong>{stats.current_streak}</strong> {t(lang, "stats.streak")}</span>
          <span>{t(lang, "stats.max")} <strong>{stats.max_streak}</strong></span>
        </div>
      )}
    </div>
  );
}
