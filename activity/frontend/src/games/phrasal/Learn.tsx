import { useEffect, useMemo, useState } from "react";
import { fetchPhrasalDeck, type PhrasalDeckEntry } from "../../api";
import { useLang } from "../../i18n/lang";
import { DEFAULT_LANG, t } from "./i18n";

interface LearnProps {
  onBack: () => void;
  accessToken: string;
  onPracticeIds?: (ids: string[]) => void;
}

const PAGE_SIZE = 10;

const DIFFICULTIES: { key: string | null; labelKey: string }[] = [
  { key: null,           labelKey: "learn.filter.all" },
  { key: "beginner",     labelKey: "learn.filter.beginner" },
  { key: "intermediate", labelKey: "learn.filter.intermediate" },
  { key: "advanced",     labelKey: "learn.filter.advanced" },
];

// Highlight the phrasal verb inside its example sentence so the learner's eye
// lands on it. Case-insensitive, first occurrence only.
function Highlighted({ example, verb }: { example: string; verb: string }) {
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

export default function Learn({ onBack, onPracticeIds }: LearnProps) {
  const [lang] = useLang(DEFAULT_LANG);
  const [difficulty, setDifficulty] = useState<string | null>(null);
  const [verbs, setVerbs] = useState<PhrasalDeckEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  useEffect(() => {
    let alive = true;
    setVerbs(null);
    setError(null);
    setPage(0);
    fetchPhrasalDeck(difficulty ?? undefined)
      .then((d) => { if (alive) setVerbs(d.verbs); })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : t(lang, "learn.error")); });
    return () => { alive = false; };
  }, [difficulty]); // lang intentionally excluded — changing lang doesn't refetch

  const total = verbs?.length ?? 0;
  const pageCount = Math.ceil(total / PAGE_SIZE);

  // The 10 entries visible on the current page.
  const pageVerbs = useMemo(
    () => verbs?.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE) ?? [],
    [verbs, page],
  );

  const pageIds = pageVerbs.map((v) => v.id);

  return (
    <div className="phrasal phrasal-learn">
      <div className="round-top">
        <button className="finish-btn" onClick={onBack}>
          {t(lang, "learn.back")}
        </button>
        {total > 0 && (
          <span className="pill pill-progress">
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} / {total}
          </span>
        )}
      </div>

      <div className="chips learn-filter">
        {DIFFICULTIES.map((dfc) => (
          <button
            key={dfc.labelKey}
            className={`chip${difficulty === dfc.key ? " chip--on" : ""}`}
            onClick={() => setDifficulty(dfc.key)}
          >
            {t(lang, dfc.labelKey)}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}
      {!verbs && !error && <p className="muted">{t(lang, "learn.loading")}</p>}

      {pageVerbs.length > 0 && (
        <ul className="learn-cards-list">
          {pageVerbs.map((entry) => (
            <li className="prompt-card learn-card" key={entry.id}>
              <div className="learn-headword">
                <span className="learn-verb">{entry.verb}</span>
                {entry.gloss_es && (
                  <span className="learn-gloss">{entry.gloss_es}</span>
                )}
              </div>

              <ul className="learn-defs">
                {entry.definitions.map((def, i) => (
                  <li key={i}>{def}</li>
                ))}
              </ul>

              <p className="learn-example">
                <Highlighted example={entry.example} verb={entry.verb} />
              </p>
            </li>
          ))}
        </ul>
      )}

      {pageCount > 1 && (
        <div className="learn-nav">
          <button
            className="cta cta-ghost"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page <= 0}
          >
            {t(lang, "learn.prev")}
          </button>
          <button
            className="cta"
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={page >= pageCount - 1}
          >
            {t(lang, "learn.next")}
          </button>
        </div>
      )}

      {/* P4: "Practicar estos 10" → freeplay with ids from this page. */}
      {onPracticeIds && pageIds.length > 0 && (
        <button
          className="cta cta-practice-page"
          onClick={() => onPracticeIds(pageIds)}
        >
          {t(lang, "learn.practice_10")}
        </button>
      )}
    </div>
  );
}
