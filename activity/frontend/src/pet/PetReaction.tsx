import { useEffect, useRef, useState } from "react";
import { fetchPet, type PetProfile } from "../api";
import Pet from "./Pet";
import type { Species } from "./model";

interface PetReactionProps {
  accessToken: string;
  outcome: "win" | "meh";
}

/** Renders the user's critter with a one-shot reaction cue on every game
 *  summary screen. Every player has a pet (a default until customised), so
 *  this only renders nothing while loading or if the fetch fails. */
export default function PetReaction({ accessToken, outcome }: PetReactionProps) {
  const [pet, setPet] = useState<PetProfile | null>(null);
  const [cueN, setCueN] = useState(0);
  const triggered = useRef(false);

  useEffect(() => {
    let cancelled = false;
    fetchPet(accessToken)
      .then((state) => {
        if (cancelled) return;
        setPet(state.pet);
        if (!triggered.current) {
          // Pet ignores the cue it mounts with; flip to n=1 ~150ms after data
          // arrives so the reaction visibly plays.
          window.setTimeout(() => {
            if (!cancelled) {
              triggered.current = true;
              setCueN(1);
            }
          }, 150);
        }
      })
      .catch(() => {
        // Summary works without the pet; nothing to show.
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  if (pet === null) return null;

  const kind = outcome === "win" ? "hop" : "squish";
  const caption = outcome === "win" ? "¡Olé!" : "Casi…";

  return (
    <div className="pet-reaction">
      <Pet
        species={pet.species as Species}
        color={pet.color}
        size={64}
        mood="idle"
        cue={{ kind, n: cueN }}
      />
      <span className="pet-reaction__caption">{caption}</span>
    </div>
  );
}
