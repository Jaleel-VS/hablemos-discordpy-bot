// Backend keys select frontend renderers; display names come from /api/games.
import type { ComponentType } from "react";
import Wordle from "./wordle/Wordle";
import Conjugation from "./conjugation/Conjugation";
import Cloze from "./cloze/Cloze";
import Phrasal from "./phrasal/Phrasal";

export interface GameProps {
  accessToken: string;
  displayName: string;
  onExit: () => void;
}

export interface GameMeta {
  tagline: string;
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
  cloze: {
    tagline: "Completa la palabra que falta",
    glyph: "▭",
    hue: 35,
    component: Cloze,
  },
  phrasal: {
    tagline: "Domina los phrasal verbs",
    glyph: "⇄",
    hue: 210,
    component: Phrasal,
  },
};
