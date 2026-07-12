import type { CSSProperties } from "react";
import type { Row, Tile } from "../../api";

interface BoardProps {
  rows: Row[];
  current: string;
  maxGuesses: number;
  wordLength: number;
  // Index of the row that was just submitted, so only it plays the flip-reveal
  // (older rows stay static). null = nothing to animate.
  revealRow: number | null;
  shake: boolean;
}

function tileClass(tile: Tile): string {
  return `tile tile--${tile}`;
}

export default function Board({
  rows,
  current,
  maxGuesses,
  wordLength,
  revealRow,
  shake,
}: BoardProps) {
  const currentRowIndex = rows.length;
  const chars = [...current]; // spread handles ñ as one unit

  return (
    <div className="board-wrap">
      <div
        className="board"
        style={{
          ["--cols" as string]: wordLength,
          ["--rows" as string]: maxGuesses,
        }}
      >
        {Array.from({ length: maxGuesses }).map((_, r) => {
          const submitted = rows[r];
          const isCurrent = r === currentRowIndex;
          const revealing = submitted != null && r === revealRow;
          const rowClass = `board-row${shake && isCurrent ? " shake" : ""}`;
          return (
            <div className={rowClass} key={r}>
              {Array.from({ length: wordLength }).map((__, c) => {
                if (submitted) {
                  const cls = `${tileClass(submitted.tiles[c])}${
                    revealing ? " tile--revealed" : ""
                  }`;
                  const style = revealing
                    ? ({ ["--i" as string]: c } as CSSProperties)
                    : undefined;
                  return (
                    <div className={cls} style={style} key={c}>
                      {[...submitted.guess][c] ?? ""}
                    </div>
                  );
                }
                const letter = isCurrent ? (chars[c] ?? "") : "";
                return (
                  <div className={`tile${letter ? " tile--filled" : ""}`} key={c}>
                    {letter}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
