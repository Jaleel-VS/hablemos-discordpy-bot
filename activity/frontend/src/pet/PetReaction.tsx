import { useEffect, useRef, useState } from "react";
import Pet from "./Pet";
import type { Species } from "./model";

interface PetData {
  species: Species;
  color: string;
  name: string;
}

interface PetResponse {
  pet: PetData | null;
}

interface PetReactionProps {
  accessToken: string;
  outcome: "win" | "meh";
}

/** Renders the user's critter with a one-shot reaction cue on every game
 *  summary screen. The component fetches the pet data once; if the user has no
 *  pet configured or the fetch fails it renders nothing. */
export default function PetReaction({ accessToken, outcome }: PetReactionProps) {
  const [pet, setPet] = useState<PetData | null | undefined>(undefined); // undefined = loading
  const [cueN, setCueN] = useState(0);
  const triggered = useRef(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/.proxy/api/pet/me", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: accessToken }),
    })
      .then((r) => r.json() as Promise<PetResponse>)
      .then((data) => {
        if (cancelled) return;
        setPet(data.pet ?? null);
        if (data.pet && !triggered.current) {
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
        if (!cancelled) setPet(null);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  if (!pet) return null;

  const kind = outcome === "win" ? "hop" : "squish";
  const caption = outcome === "win" ? "¡Olé!" : "Casi…";

  return (
    <div className="pet-reaction">
      <Pet
        species={pet.species}
        color={pet.color}
        size={64}
        mood="idle"
        cue={{ kind, n: cueN }}
      />
      <span className="pet-reaction__caption">{caption}</span>
    </div>
  );
}
