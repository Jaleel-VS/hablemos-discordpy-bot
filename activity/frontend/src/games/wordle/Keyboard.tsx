import type { Row, Tile } from "../../api";
import type { Lang } from "../../i18n/lang";
import { t } from "./i18n";

interface KeyboardProps {
  rows: Row[];
  onKey: (key: string) => void;
  disabled: boolean;
  lang: Lang;
}

// Spanish keyboard layout including Ñ. ENTER and ⌫ (backspace) are special.
const LAYOUT = [
  ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
  ["a", "s", "d", "f", "g", "h", "j", "k", "l", "ñ"],
  ["ENTER", "z", "x", "c", "v", "b", "n", "m", "⌫"],
];

// Best-known state per letter across all submitted rows. Green beats yellow
// beats gray so a key never "downgrades" once it's been green.
function letterStates(rows: Row[]): Record<string, Tile> {
  const rank: Record<Tile, number> = { gray: 0, yellow: 1, green: 2 };
  const best: Record<string, Tile> = {};
  for (const row of rows) {
    const letters = [...row.guess];
    letters.forEach((ch, i) => {
      const tile = row.tiles[i];
      if (!(ch in best) || rank[tile] > rank[best[ch]]) {
        best[ch] = tile;
      }
    });
  }
  return best;
}

export default function Keyboard({ rows, onKey, disabled, lang }: KeyboardProps) {
  const states = letterStates(rows);

  return (
    <div className="keyboard">
      {LAYOUT.map((keyRow, i) => (
        <div className="keyboard-row" key={i}>
          {keyRow.map((key) => {
            const isEnter = key === "ENTER";
            const isDelete = key === "⌫";
            const special = isEnter || isDelete;
            const state = !special ? states[key] : undefined;
            const cls = [
              "key",
              special ? "key--wide" : "",
              state ? `key--${state}` : "",
            ]
              .filter(Boolean)
              .join(" ");
            const ariaLabel = isEnter
              ? t(lang, "key.enter")
              : isDelete
              ? t(lang, "key.delete")
              : key;
            return (
              <button
                key={key}
                className={cls}
                disabled={disabled}
                onClick={() => onKey(key)}
                aria-label={ariaLabel}
                style={{ touchAction: "manipulation" }}
              >
                {key}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
