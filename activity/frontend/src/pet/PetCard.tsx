// PetCard: the player's critter shown above the game list on the hub.
// Every player has a pet from the first visit (the server derives a default
// from their id), so the card shows it straight away: arcade cabinet bezel,
// status line, weekly stats, and a ghost "Cambiar" button that opens
// PetPicker to change species, colour and name.
import { useEffect, useRef, useState } from "react";
import type { GameInfo, PetState } from "../api";
import { fetchPet } from "../api";
import { GAME_REGISTRY } from "../games/registry";
import Pet from "./Pet";
import PetPicker from "./PetPicker";
import { SPECIES_NAMES, type Species } from "./model";

interface PetCardProps {
  accessToken: string;
  /** Registered games, for the favourite-game display name. */
  games: GameInfo[];
  /** Called once the pet state resolves (so Home can read streak_days). */
  onStreak?: (state: PetState) => void;
}

type CardPhase =
  | { kind: "loading" }
  | { kind: "failed" }
  | { kind: "ready"; state: PetState }
  | { kind: "picking"; state: PetState };

function statusLine(state: PetState): string {
  const { mood, streak_days: streak, played_today } = state;
  if (mood === "happy" && played_today) {
    return streak >= 3 ? `Día ${streak} · ¡racha!` : `Hoy ya jugaste · día ${streak}`;
  }
  if (played_today) {
    return `Hoy ya jugaste · día ${streak}`;
  }
  if (mood === "waiting") {
    return `Te espera · día ${streak} en juego`;
  }
  if (mood === "sleepy") {
    return "Dormido… vuelve a jugar";
  }
  return "Toca para saludar";
}

export default function PetCard({ accessToken, games, onStreak }: PetCardProps) {
  const [phase, setPhase] = useState<CardPhase>({ kind: "loading" });
  // hop cue counter: increment once on load when mood is happy
  const hopSent = useRef(false);
  const [hopN, setHopN] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchPet(accessToken)
      .then((state) => {
        if (cancelled) return;
        setPhase({ kind: "ready", state });
        onStreak?.(state);
        if (state.mood === "happy" && !hopSent.current) {
          hopSent.current = true;
          setHopN(1);
        }
      })
      .catch(() => {
        // No pet to show; the hub works without it.
        if (!cancelled) setPhase({ kind: "failed" });
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  function onDone(state: PetState) {
    setPhase({ kind: "ready", state });
    onStreak?.(state);
    hopSent.current = false;
    if (state.mood === "happy") {
      hopSent.current = true;
      setHopN((n) => n + 1);
    }
  }

  // Reserve layout space while loading (avoids jump when pet arrives)
  if (phase.kind === "loading") {
    return <div className="pet-card pet-card--loading" aria-hidden />;
  }
  if (phase.kind === "failed") return null;

  if (phase.kind === "picking") {
    const prev = phase.state;
    return (
      <div className="pet-card pet-card--picking">
        <PetPicker
          accessToken={accessToken}
          initial={{
            species: prev.pet.species as Species,
            color: prev.pet.color,
            name: prev.pet.name,
          }}
          onDone={onDone}
          onCancel={() => setPhase({ kind: "ready", state: prev })}
        />
      </div>
    );
  }

  const { state } = phase;
  const { pet, mood, games_this_week, favorite_game } = state;

  const displayName = pet.name || SPECIES_NAMES[pet.species as Species] || pet.species;
  const isHappy = mood === "happy";
  const favInfo = favorite_game ? games.find((g) => g.key === favorite_game) : undefined;
  const favMeta = favorite_game ? GAME_REGISTRY[favorite_game] : undefined;
  const favLabel = favInfo && favMeta ? `${favMeta.glyph} ${favInfo.display_name}` : null;

  return (
    <div className="pet-card" aria-label={`Tu mascota: ${displayName}`}>
      {/* arcade cabinet bezel */}
      <div className="pet-card-bezel">
        <div className="pet-card-screen">
          <Pet
            species={pet.species as Species}
            color={pet.color}
            size={80}
            interactive
            mood="idle"
            cue={isHappy ? { kind: "hop", n: hopN } : undefined}
            label={displayName}
          />
        </div>
      </div>
      <div className="pet-card-info">
        <span className="pet-card-name">{displayName.toUpperCase()}</span>
        <span className="pet-card-status">{statusLine(state)}</span>
        <span className="pet-card-stats">
          {games_this_week} partida{games_this_week !== 1 ? "s" : ""} esta semana
          {favLabel !== null && <span className="pet-card-fav">{favLabel}</span>}
        </span>
        <button
          type="button"
          className="pet-card-change"
          aria-label="Cambiar mascota"
          onClick={() => setPhase({ kind: "picking", state })}
        >
          Cambiar
        </button>
      </div>
    </div>
  );
}
