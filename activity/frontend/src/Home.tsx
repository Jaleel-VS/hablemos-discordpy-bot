import type { CSSProperties } from "react";
import type { GameInfo } from "./api";
import { GAME_REGISTRY } from "./games/registry";

interface HomeProps {
  games: GameInfo[];
  onPick: (key: string) => void;
}

// The hub. Lists every registered game as a full-bleed row the player taps to
// enter. Deliberately not a grid of identical cards (an AI-slop tell) — each
// game is a wide row carrying its own accent hue and oversized glyph, stacked
// with editorial rhythm. Only shown when 2+ games exist; a single game boots
// straight in (see App.tsx).
export default function Home({ games, onPick }: HomeProps) {
  const known = games.filter((g) => GAME_REGISTRY[g.key]);
  return (
    <div className="home">
      <div className="home-head">
        <h1 className="home-title">Juegos</h1>
        <p className="home-sub">Elige cómo practicar hoy</p>
      </div>
      <ul className="home-list">
        {known.map((g, i) => {
          const meta = GAME_REGISTRY[g.key];
          const style = {
            ["--game-hue" as string]: meta.hue,
            ["--i" as string]: i,
          } as CSSProperties;
          return (
            <li key={g.key}>
              <button className="game-row" style={style} onClick={() => onPick(g.key)}>
                <span className="game-glyph" aria-hidden>
                  {meta.glyph}
                </span>
                <span className="game-copy">
                  <span className="game-name">{g.display_name}</span>
                  <span className="game-tagline">{meta.tagline}</span>
                </span>
                <span className="game-go" aria-hidden>
                  →
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
