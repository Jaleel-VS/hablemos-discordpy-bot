"""Curated starter cards for the Vocab Catch pool.

A small, quality bidirectional seed across all five rarities. Loaded by
``$vocatchadmin seed`` (idempotent: only inserts when the pool is empty).
Words skew commoner at low rarity, trickier/rarer at high rarity.

Each entry: (word_es, word_en, part_of_speech, gender, example_es,
example_en, rarity).
"""

# rarity 1 = Common ... 5 = Legendary
SEED_CARDS: list[tuple[str, str, str, str | None, str | None, str | None, int]] = [
    # ── Common (everyday words) ──
    ("la casa", "the house", "sustantivo", "la",
     "Vivimos en una casa pequeña.", "We live in a small house.", 1),
    ("el agua", "water", "sustantivo", "el",
     "Bebe mucha agua cada día.", "Drink lots of water every day.", 1),
    ("comer", "to eat", "verbo", None,
     "Me gusta comer fruta.", "I like to eat fruit.", 1),
    ("el perro", "the dog", "sustantivo", "el",
     "El perro corre en el parque.", "The dog runs in the park.", 1),
    ("bueno", "good", "adjetivo", None,
     "Es un buen libro.", "It is a good book.", 1),
    ("hablar", "to speak", "verbo", None,
     "Quiero hablar español.", "I want to speak Spanish.", 1),
    # ── Uncommon ──
    ("el puente", "the bridge", "sustantivo", "el",
     "Cruzamos el puente al amanecer.", "We crossed the bridge at dawn.", 2),
    ("alegre", "cheerful", "adjetivo", None,
     "Ella siempre está alegre.", "She is always cheerful.", 2),
    ("la nube", "the cloud", "sustantivo", "la",
     "Una nube cubrió el sol.", "A cloud covered the sun.", 2),
    ("construir", "to build", "verbo", None,
     "Van a construir una escuela.", "They are going to build a school.", 2),
    # ── Rare ──
    ("el atardecer", "the sunset", "sustantivo", "el",
     "El atardecer pintó el cielo de naranja.", "The sunset painted the sky orange.", 3),
    ("susurrar", "to whisper", "verbo", None,
     "Le susurró un secreto al oído.", "He whispered a secret in her ear.", 3),
    ("la mariposa", "the butterfly", "sustantivo", "la",
     "Una mariposa se posó en la flor.", "A butterfly landed on the flower.", 3),
    # ── Epic ──
    ("el relámpago", "lightning", "sustantivo", "el",
     "El relámpago iluminó el cielo nocturno.", "The lightning lit up the night sky.", 4),
    ("efímero", "ephemeral", "adjetivo", None,
     "La belleza del momento fue efímera.", "The beauty of the moment was ephemeral.", 4),
    ("el crepúsculo", "twilight", "sustantivo", "el",
     "Caminamos durante el crepúsculo.", "We walked during the twilight.", 4),
    # ── Legendary ──
    ("la inquietud", "restlessness", "sustantivo", "la",
     "Una inquietud extraña lo invadió.", "A strange restlessness overcame him.", 5),
    ("inefable", "ineffable", "adjetivo", None,
     "Sintió una alegría inefable.", "He felt an ineffable joy.", 5),
]
