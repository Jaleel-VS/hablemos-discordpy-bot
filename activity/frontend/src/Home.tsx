import { useMemo, useState } from "react";
import type { GameInfo, PetState } from "./api";
import { GAME_REGISTRY } from "./games/registry";
import Leaderboard from "./Leaderboard";
import PetCard from "./pet/PetCard";

interface HomeProps {
  games: GameInfo[];
  onPick: (key: string) => void;
  accessToken: string;
  userId: string;
  // The server leaderboard only exists inside a server (not in DMs).
  inGuild: boolean;
}

/** Spanish weekday + date, e.g. "Jueves 9 oct" */
function todayLabel(): string {
  const now = new Date();
  const fmt = new Intl.DateTimeFormat("es", {
    weekday: "long",
    day: "numeric",
    month: "short",
  });
  const parts = fmt.formatToParts(now);
  const weekday = parts.find((p) => p.type === "weekday")?.value ?? "";
  const day = parts.find((p) => p.type === "day")?.value ?? "";
  const month = parts.find((p) => p.type === "month")?.value ?? "";
  return `${weekday.charAt(0).toUpperCase() + weekday.slice(1)} ${day} ${month}`;
}

// The hub. Lists every registered game as a select-screen row the player taps to
// enter. Title in pixel face with a blinking cursor, date + streak sub-line,
// pet cabinet, game select list, leaderboard.
export default function Home({ games, onPick, accessToken, userId, inGuild }: HomeProps) {
  const known = games.filter((g) => GAME_REGISTRY[g.key]);
  const dateStr = useMemo(todayLabel, []);
  const [streakDays, setStreakDays] = useState(0);

  // PetCard calls onStreak once the pet state resolves.
  const handleStreak = useMemo(
    () => (state: PetState) => setStreakDays(state.streak_days ?? 0),
    [],
  );

  const subLine = streakDays > 0
    ? `${dateStr} · racha ×${streakDays}`
    : dateStr;

  // First row is always the "selected" cursor default (PRESS START for all;
  // per-game today data is not available in the API without extra calls).
  const selIndex = 0;

  return (
    <div className="home">
      <div className="home-head">
        <h1 className="home-title">
          Elige tu juego<span className="home-cursor" aria-hidden>_</span>
        </h1>
        <p className="home-sub">{subLine}</p>
      </div>
      <PetCard accessToken={accessToken} games={known} onStreak={handleStreak} />
      <ul className="home-list">
        {known.map((g, i) => {
          const meta = GAME_REGISTRY[g.key];
          return (
            <li key={g.key}>
              <button
                className={`game-row${i === selIndex ? " game-row--sel" : ""}`}
                onClick={() => onPick(g.key)}
              >
                <span className="game-cursor" aria-hidden>▶</span>
                <span className="game-copy">
                  <span className="game-name">{g.display_name.toUpperCase()}</span>
                  <span className="game-tagline">{meta.tagline}</span>
                </span>
                <span className="game-state">PRESS START</span>
              </button>
            </li>
          );
        })}
      </ul>
      {inGuild && <Leaderboard games={known} accessToken={accessToken} userId={userId} />}
    </div>
  );
}
