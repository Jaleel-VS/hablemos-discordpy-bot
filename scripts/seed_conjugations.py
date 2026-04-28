"""Seed conjugation_verbs and conjugation_forms from the Fred Jehle dataset."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg2  # type: ignore[import-untyped]

DB_URL = sys.argv[1] if len(sys.argv) > 1 else "postgresql://postgres:SYKziTVKhRlHCEpeGyEUmNcXKarGJrVP@yamanote.proxy.rlwy.net:43988/railway"
JEHLE_PATH = Path("/tmp/jehle.json")

# Jehle mood/tense → our tense key mapping (A1–B2 only)
TENSE_MAP: dict[tuple[str, str], tuple[str, str]] = {
    # (jehle_mood, jehle_tense) → (our_key, level)
    ("Indicative", "Present"): ("presente", "A1"),
    ("Indicative", "Preterite"): ("pretérito", "A2"),
    ("Indicative", "Imperfect"): ("imperfecto", "A2"),
    ("Indicative", "Future"): ("futuro", "A2"),
    ("Indicative", "Conditional"): ("condicional", "B1"),
    ("Indicative", "Present Perfect"): ("pretérito_perfecto", "B1"),
    ("Indicative", "Past Perfect"): ("pluscuamperfecto", "B2"),
    ("Subjunctive", "Present"): ("subjuntivo_presente", "B1"),
    ("Subjunctive", "Imperfect"): ("subjuntivo_imperfecto", "B2"),
    ("Imperative Affirmative", "Present"): ("imperativo_afirmativo", "A2"),
    ("Imperative Negative", "Present"): ("imperativo_negativo", "B1"),
}

# Normalize Jehle pronouns to our standard set
PRONOUN_MAP: dict[str, str] = {
    "yo": "yo",
    "tú": "tú",
    "él/ella/usted": "él/ella",
    "nosotros": "nosotros",
    "vosotros": "vosotros",
    "ellos/ellas/ustedes": "ellos/ellas",
}

# Top verbs by frequency for category assignment
TOP_50 = {
    "ser", "estar", "poder", "tener", "haber", "hacer", "decir", "ver", "deber", "ir",
    "dar", "parecer", "llegar", "tratar", "saber", "hablar", "querer", "poner", "dejar",
    "pasar", "llevar", "seguir", "existir", "conocer", "tomar", "salir", "encontrar",
    "crear", "evitar", "quedar", "pensar", "mantener", "realizar", "volver", "venir",
    "permitir", "resultar", "vivir", "buscar", "producir", "entrar", "conseguir", "contar",
    "considerar", "señalar", "presentar", "perder", "aparecer", "trabajar", "entender",
}


def classify_verb(infinitive: str) -> str:
    """Assign a category based on verb ending and regularity."""
    if infinitive in TOP_50:
        return "high-frequency"
    if infinitive.endswith("ar"):
        return "regular-ar"
    if infinitive.endswith("er"):
        return "regular-er"
    if infinitive.endswith("ir"):
        return "regular-ir"
    return "other"


def main() -> None:
    if not JEHLE_PATH.exists():
        print(f"Download jehle.json first: curl -sL https://raw.githubusercontent.com/ghidinelli/fred-jehle-spanish-verbs/master/jehle_verb_lookup.json -o {JEHLE_PATH}")
        sys.exit(1)

    with open(JEHLE_PATH, encoding="utf-8") as f:
        data: dict = json.load(f)

    # Collect verb info and forms
    verbs: dict[str, str] = {}  # infinitive → english
    forms: list[tuple[str, str, str, str]] = []  # (infinitive, tense_key, pronoun, form)

    for conjugated_form, entries in data.items():
        for e in entries:
            if "mood" not in e:
                continue
            key = (e["mood"], e["tense"])
            if key not in TENSE_MAP:
                continue
            pronoun = PRONOUN_MAP.get(e["performer"])
            if pronoun is None:
                continue

            tense_key, _ = TENSE_MAP[key]
            infinitive = e["infinitive"]
            verbs[infinitive] = e.get("translation", "")
            forms.append((infinitive, tense_key, pronoun, conjugated_form))

    print(f"Parsed {len(verbs)} verbs, {len(forms)} forms")

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Insert verbs (small batch, commit immediately)
    verb_ids: dict[str, int] = {}
    for i, (infinitive, english) in enumerate(sorted(verbs.items()), 1):
        category = classify_verb(infinitive)
        cur.execute(
            """INSERT INTO conjugation_verbs (infinitive, english, category, frequency_rank)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (infinitive) DO UPDATE SET english = EXCLUDED.english
               RETURNING id""",
            (infinitive, english.replace("\r", ""), category, i),
        )
        verb_ids[infinitive] = cur.fetchone()[0]
    conn.commit()
    print(f"Inserted {len(verb_ids)} verbs")

    # Insert forms in batches of 1000
    BATCH = 1000
    batch_values: list[tuple] = []
    inserted = 0
    for infinitive, tense_key, pronoun, form in forms:
        vid = verb_ids.get(infinitive)
        if vid is None:
            continue
        batch_values.append((vid, tense_key, pronoun, form))
        if len(batch_values) >= BATCH:
            cur.executemany(
                """INSERT INTO conjugation_forms (verb_id, tense, pronoun, form)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (verb_id, tense, pronoun) DO NOTHING""",
                batch_values,
            )
            conn.commit()
            inserted += len(batch_values)
            print(f"  ... {inserted}/{len(forms)} forms")
            batch_values = []
    if batch_values:
        cur.executemany(
            """INSERT INTO conjugation_forms (verb_id, tense, pronoun, form)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (verb_id, tense, pronoun) DO NOTHING""",
            batch_values,
        )
        conn.commit()
        inserted += len(batch_values)

    print(f"Inserted {inserted} conjugation forms")

    # Summary
    cur.execute("SELECT count(*) FROM conjugation_verbs")
    print(f"Total verbs in DB: {cur.fetchone()[0]}")
    cur.execute("SELECT tense, count(*) FROM conjugation_forms GROUP BY tense ORDER BY tense")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} forms")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
