import { useEffect, useMemo, useState } from "react";
import { fetchPhrasalDeck, type PhrasalDeckEntry } from "../../api";

interface LearnProps {
  onBack: () => void;
}

const DIFFICULTIES: { key: string | null; label: string }[] = [
  { key: null, label: "Todos" },
  { key: "beginner", label: "Principiante" },
  { key: "intermediate", label: "Intermedio" },
  { key: "advanced", label: "Avanzado" },
];

// Highlight the phrasal verb inside its example sentence so the learner's eye
// lands on it. Case-insensitive, first occurrence only.
function highlight(example: string, verb: string) {
  const idx = example.toLowerCase().indexOf(verb.toLowerCase());
  if (idx === -1) return <>{example}</>;
  return (
    <>
      {example.slice(0, idx)}
      <strong className="learn-verb-in-ctx">{example.slice(idx, idx + verb.length)}</strong>
      {example.slice(idx + verb.length)}
    </>
  );
}

export default function Learn({ onBack }: LearnProps) {
  const [difficulty, setDifficulty] = useState<string | null>(null);
  const [verbs, setVerbs] = useState<PhrasalDeckEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    let alive = true;
    setVerbs(null);
    setError(null);
    setIdx(0);
    fetchPhrasalDeck(difficulty ?? undefined)
      .then((d) => {
        if (alive) setVerbs(d.verbs);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : "No se pudo cargar");
      });
    return () => {
      alive = false;
    };
  }, [difficulty]);

  const current = useMemo(
    () => (verbs && verbs.length > 0 ? verbs[Math.min(idx, verbs.length - 1)] : null),
    [verbs, idx],
  );

  const total = verbs?.length ?? 0;
  const prev = () => setIdx((i) => Math.max(0, i - 1));
  const next = () => setIdx((i) => Math.min(total - 1, i + 1));

  return (
    <div className="phrasal phrasal-learn">
      <div className="round-top">
        <button className="finish-btn" onClick={onBack}>
          ← Atrás
        </button>
        {total > 0 && (
          <span className="pill pill-progress">
            {Math.min(idx + 1, total)} / {total}
          </span>
        )}
      </div>

      <div className="chips learn-filter">
        {DIFFICULTIES.map((dfc) => (
          <button
            key={dfc.label}
            className={`chip${difficulty === dfc.key ? " chip--on" : ""}`}
            onClick={() => setDifficulty(dfc.key)}
          >
            {dfc.label}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}
      {!verbs && !error && <p className="muted">Cargando…</p>}

      {current && (
        <div className="prompt-card learn-card" key={current.id}>
          <div className="learn-headword">
            <span className="learn-verb">{current.verb}</span>
            {current.gloss_es && <span className="learn-gloss">{current.gloss_es}</span>}
          </div>

          <ul className="learn-defs">
            {current.definitions.map((def, i) => (
              <li key={i}>{def}</li>
            ))}
          </ul>

          <p className="learn-example">{highlight(current.example, current.verb)}</p>
        </div>
      )}

      {total > 0 && (
        <div className="learn-nav">
          <button className="cta cta-ghost" onClick={prev} disabled={idx <= 0}>
            ← Anterior
          </button>
          <button className="cta" onClick={next} disabled={idx >= total - 1}>
            Siguiente →
          </button>
        </div>
      )}
    </div>
  );
}
