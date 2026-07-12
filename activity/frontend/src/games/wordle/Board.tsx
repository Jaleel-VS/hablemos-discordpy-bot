import type { Row, Tile } from "../../api";

interface BoardProps {
  rows: Row[];
  current: string;
  maxGuesses: number;
  wordLength: number;
}

function tileClass(tile: Tile): string {
  return `tile tile--${tile}`;
}

// Render the fixed maxGuesses x wordLength grid: submitted rows (scored),
// the in-progress row, then empty rows.
export default function Board({ rows, current, maxGuesses, wordLength }: BoardProps) {
  const currentRowIndex = rows.length;
  const chars = [...current]; // spread handles ñ as one unit

  return (
    <div className="board" style={{ ["--cols" as string]: wordLength }}>
      {Array.from({ length: maxGuesses }).map((_, r) => {
        const submitted = rows[r];
        const isCurrent = r === currentRowIndex;
        return (
          <div className="board-row" key={r}>
            {Array.from({ length: wordLength }).map((__, c) => {
              if (submitted) {
                return (
                  <div className={tileClass(submitted.tiles[c])} key={c}>
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
  );
}
