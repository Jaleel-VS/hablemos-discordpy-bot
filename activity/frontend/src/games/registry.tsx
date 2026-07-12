// Frontend game registry — mirrors the backend's registry.py. The menu lists
// whatever `GET /api/games` returns; this map tells the app which component
// renders a given game key and how to present it on the home screen.
//
// Adding a game = add one entry here + its component. The launch boundary
// (App.tsx) needs no change.
import type { ComponentType } from "react";
import Wordle from "./wordle/Wordle";
import Conjugation from "./conjugation/Conjugation";

export interface GameProps {
  accessToken: string;
  onExit: () => void;
}

export interface GameMeta {
  // Short tagline for the home card.
  tagline: string;
  // A single emoji glyph used as the card's mark.
  glyph: string;
  // Accent hue (OKLCH H) so each game card carries its own identity.
  hue: number;
  component: ComponentType<GameProps>;
}

export const GAME_REGISTRY: Record<string, GameMeta> = {
  wordle: {
    tagline: "Adivina la palabra del día",
    glyph: "◧",
    hue: 155,
    component: Wordle,
  },
  conjugation: {
    tagline: "Conjuga contra el reloj",
    glyph: "↻",
    hue: 285,
    component: Conjugation,
  },
};
