import type { RefObject } from "react";

interface AccentBarProps {
  inputRef: RefObject<HTMLInputElement | null>;
  value: string;
  onChange: (value: string) => void;
}

const ACCENTS = [
  { char: "á", label: "a con tilde" },
  { char: "é", label: "e con tilde" },
  { char: "í", label: "i con tilde" },
  { char: "ó", label: "o con tilde" },
  { char: "ú", label: "u con tilde" },
  { char: "ñ", label: "eñe" },
  { char: "ü", label: "u con diéresis" },
];

/** Insert a character at the current caret position, restoring focus. */
function insertAtCaret(
  inputEl: HTMLInputElement,
  char: string,
  value: string,
  onChange: (v: string) => void,
): void {
  const start = inputEl.selectionStart ?? value.length;
  const end = inputEl.selectionEnd ?? value.length;
  const next = value.slice(0, start) + char + value.slice(end);
  onChange(next);
  // Restore focus and advance cursor after the inserted char (RAF so React
  // flushes the value update before we touch selectionRange).
  requestAnimationFrame(() => {
    inputEl.focus();
    const pos = start + char.length;
    inputEl.setSelectionRange(pos, pos);
  });
}

export default function AccentBar({ inputRef, value, onChange }: AccentBarProps) {
  return (
    <div className="accent-bar" role="toolbar" aria-label="Accent shortcuts">
      {ACCENTS.map(({ char, label }) => (
        <button
          key={char}
          type="button"
          className="accent-btn"
          aria-label={label}
          onPointerDown={(e) => {
            // Prevent the button from stealing focus from the input before we
            // can read selectionStart/End.
            e.preventDefault();
            const el = inputRef.current;
            if (!el) return;
            insertAtCaret(el, char, value, onChange);
          }}
        >
          {char}
        </button>
      ))}
    </div>
  );
}
