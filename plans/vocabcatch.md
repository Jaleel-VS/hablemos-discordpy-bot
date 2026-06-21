# Vocab Catch — design spec

A Pokétwo/Pokécord-style "catch the card" minigame for Spanish vocab.
A premium Pillow-rendered vocab card spawns in a busy channel; the first
player to type `catch <word>` claims it into their collection. Rarer
cards spawn less often and score more.

Status: **design locked, not yet implemented.**

## Decisions (locked)

| Question | Decision |
|----------|----------|
| Capture method | Type the **Spanish word** shown on the card |
| Capture trigger | Bare `catch <word>` (no prefix) — matched in `on_message` |
| Rarity | 5 tiers: Common → Uncommon → Rare → Epic → Legendary |
| Word source | New curated `vocab_card_pool` table (seeded) |
| Spawn scope | Single configurable channel |
| Translation on card | **Hidden** until caught (unlocked on capture) |
| Duplicates | Allowed — increments a per-user count (`xN`) |
| Scoring | Own points by rarity + dedicated leaderboard |

> Note: this is **separate** from `vocab_notes` (per-user personal
> notes). The card pool is a curated, shared, game-only word bank.

## Game loop

1. **Spawn** — an `on_message` listener counts non-bot messages in the
   configured channel. Once the count crosses a threshold (with a
   minimum cooldown + random jitter so it feels organic and isn't
   farmable), pick a card by rarity weight and post:
   - a Pillow-rendered card image (translation hidden),
   - a short embed/line: "A wild word appeared! Type `catch <word>` to
     catch it."
   - Only one active spawn per channel at a time.
2. **Capture** — players type `catch <word>`. Match is
   case-insensitive and accent-insensitive (`catch nino` catches
   `niño`). First valid catch wins (guarded against races — see below).
3. **Claim** — on first valid catch:
   - edit the spawn message to reveal the translation + "Caught by
     @user (xN)",
   - insert/upsert the catch row, award rarity points,
   - clear the active spawn.
   Late/incorrect attempts are ignored (or a soft "too late!" on a
   correct-but-late guess).
4. **Collection** — `$vocadex` shows the user's caught cards (rarity
   counts, total points); `$vocadex <card_id>` re-renders one card.

## Card anatomy (Pillow, premium look)

Follow the house super-sampling convention (see
`docs/architecture.md#image-rendering-pillow` and
`cogs/league_cog/league_helper/leaderboard_image_pillow.py`): render the
whole canvas at `S` (super-sample multiplier), scale every coordinate by
`S`, then LANCZOS-downsample to the export size. `get_font` already
multiplies the requested size by `S`.

Elements:
- **Rarity-tinted frame** — per-tier border color + optional foil/holo
  gradient for Epic/Legendary. This is the collectible "wow".
- **Spanish word** — hero element, large, centered. Script accent font
  (e.g. `SatisfyPro.ttf`) for high rarity; Helvetica for body.
- **Part-of-speech + gender chip** — e.g. `el · sustantivo`.
- **Translation** — rendered as `？？？` on spawn; the caught/`$vocadex`
  render shows the real translation.
- **Example sentence** — small italic, optional.
- **Footer** — rarity label + card number (`#0042`) + (high rarity) a
  subtle holographic texture.

Fonts live in `cogs/league_cog/league_helper/fonts/` (Helvetica,
SatisfyPro, etc.). Reuse, don't duplicate.

## Data model (new tables — `db/schema.py`)

```sql
-- Curated, shared word bank for the game.
CREATE TABLE IF NOT EXISTS vocab_card_pool (
    card_id        SERIAL PRIMARY KEY,
    word           TEXT NOT NULL,
    translation    TEXT NOT NULL,
    part_of_speech TEXT,             -- 'sustantivo', 'verbo', ...
    gender         TEXT,             -- 'el' | 'la' | NULL
    example        TEXT,             -- example sentence (optional)
    rarity         SMALLINT NOT NULL DEFAULT 1,  -- 1..5
    language       TEXT NOT NULL DEFAULT 'es',
    active         BOOLEAN NOT NULL DEFAULT TRUE
);

-- Who caught what (the inventory). Dupes increment count.
CREATE TABLE IF NOT EXISTS vocab_card_catches (
    user_id      BIGINT NOT NULL,
    card_id      INTEGER NOT NULL REFERENCES vocab_card_pool(card_id),
    count        INTEGER NOT NULL DEFAULT 1,
    first_caught TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_caught  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, card_id)
);

CREATE INDEX IF NOT EXISTS idx_vocabcatch_user ON vocab_card_catches(user_id);
```

Active spawn state is held **in memory** per channel (a dict on the cog)
— a spawn is ephemeral and doesn't need to survive a restart; a restart
simply clears any pending wild card.

New DB mixin `VocabCatchMixin` (`db/vocab_catch.py`), added to the
`Database` composition in `db/__init__.py`:
- `get_random_card_by_weight()` — weighted pick from `vocab_card_pool`.
- `record_catch(user_id, card_id)` — upsert + increment, returns new count.
- `get_user_collection(user_id, limit)` — joined rows for `$vocadex`.
- `get_catch_leaderboard(limit)` — points/totals per user.
- `get_card(card_id)` — single card for re-render.
- seed helpers / admin insert.

## Cog layout (`cogs/vocabcatch_cog/`)

```
__init__.py    — empty (package marker)
main.py        — VocabCatch cog: on_message (spawn + catch), $vocadex,
                 $vocatchtop, setup()
renderer.py    — render_card(card, *, revealed) -> BytesIO (Pillow)
config.py      — channel ID, spawn threshold/cooldown/jitter, rarity
                 weights, rarity colors, point values (centralized env helpers)
admin.py       — WCBetAdmin-style owner group $vocatchadmin:
                 spawn (force), addcard, reload, stats
seed.py        — initial curated card list (or a JSON the seed reads)
```

## Config (`config.py`, via centralized env helpers)

| Constant | Default | Purpose |
|----------|---------|---------|
| `VOCATCH_CHANNEL_ID` | env | Channel where cards spawn |
| `VOCATCH_SPAWN_EVERY` | 25 | Messages between spawn checks |
| `VOCATCH_SPAWN_JITTER` | 10 | ± random jitter on the threshold |
| `VOCATCH_SPAWN_COOLDOWN_S` | 120 | Min seconds between spawns |
| `VOCATCH_RARITY_WEIGHTS` | 60/25/10/4/1 | Spawn odds per tier |
| `VOCATCH_RARITY_POINTS` | 1/3/8/15/25 | Points per tier |

Rarity colors/labels also centralized in `config.py`.

## Reused patterns / AGENTS rules to honor

- **Incremental `on_message` tracking**, never history scanning.
- **Suppress repeated errors on the hot path** (`on_message`); wrap
  rendering/DB in try/except, log once.
- **Pillow super-sample at `S`**, scale all coords by `S`,
  LANCZOS-downsample (see architecture doc). `get_font` already ×S.
- **No raw SQL in the cog** — all queries via the new DB mixin.
- **No hardcoded IDs** — channel/role IDs via `config.py` + env helpers.
- **Embed helpers** from `cogs/utils/embeds.py`.
- **`pathlib.Path`** for font/asset loading.
- **Cooldowns** on `$vocadex`/leaderboard to prevent spam.
- **Slash sync** not relevant (prefix + on_message), but if any slash is
  added, sync stays manual via `$sync`.

## Edge cases / race conditions

- **Catch race**: two users type `catch <word>` near-simultaneously.
  Resolve in-process: guard the active-spawn dict with an `asyncio.Lock`
  per channel (or atomic pop) so exactly one catch wins; the DB upsert
  is then never contended for the "who was first" decision.
- **Restart**: in-memory spawn is lost — acceptable; next threshold
  spawns a fresh card.
- **Accent/case folding**: normalize both sides (NFKD strip diacritics +
  casefold) so `catch nino` == `niño`. Keep the original spelling on the
  card and in the collection.
- **Wrong-channel catches**: only listen in `VOCATCH_CHANNEL_ID`.
- **Spam farming**: cooldown + jitter; ignore the spawner's own
  immediate catch? (open question — probably fine to allow.)
- **Bot/self/webhook messages**: ignored for both spawn counting and
  catching.

## Open questions for build time

- Exact rarity palette (hex per tier) + whether Legendary gets an
  animated/holo treatment (static foil is simplest).
- Whether example sentences ship in the first seed or come later.
- Collection pagination style — reuse the wcbet `My bets`/history
  Components-V2 paging, or a simple Pillow grid sheet.

## Build order (proposed)

## Card design — LOCKED (Direction C+)

After rendering three directions (A dark-foil, B light-premium, C holo)
and researching premium TCG design (fonts drive authenticity; holo
shines on light areas / goes matte on dark; rarity must read at a
glance), we locked a refined **holo gradient** card ("C+"). The
experiment harness lives at `/tmp/vocatch_exp/` (not in the repo);
ported into `cogs/vocabcatch_cog/renderer.py`.

Final card spec (2.5:3.5 ratio, 360x504 logical px, super-sampled at
`S=4`, LANCZOS down, exported as **RGBA PNG** for rounded corners):

- **Holo frame** — diagonal gradient in the rarity colors, with a faint
  white diagonal sheen + dot pattern *only on the bright frame* (foil
  shines on light areas; the dark panel stays matte for legibility).
- **Legendary = rainbow rare** — the frame is a multi-hue HSV sweep
  (red→violet) instead of single-hue gold.
- **Dark content panel** — near-black (#101116), rounded (radius 22×S),
  inset 14×S to reveal the holo frame.
- **Background watermark** — giant faded first letter of the word (article
  ignored), rarity-tinted at ~10% alpha, behind the hero for depth.
- **Header** — rarity name in tracked condensed caps (Inter Bold) +
  a 5-pip row (●●●●○) in the rarity color.
- **Hero word** — Fraunces Black, the star; auto-shrinks by length.
- **Chip** — `el  ·  sustantivo` (Inter Medium, muted).
- **Divider** — rarity-color rule.
- **Translation** — hidden on spawn (`• • •` + `type catch <word>` hint);
  revealed on catch in rarity color (Sora SemiBold).
- **Example** — italic serif (Spectral Italic), wrapped, revealed only.
- **Footer** — card number `#0042` (Inter SemiBold, tracked).
- **Escalation** — Common flat slate → … → Epic violet → Legendary
  rainbow + outer glow (Epic/Legendary) + corner flourishes (Legendary).
- **Rounded outer corners** (radius 26) via an alpha mask.

**Fonts (all SIL OFL — free to vendor/redistribute):**
- Fraunces (display serif) — hero word + watermark
- Sora (geometric sans) — translation
- Inter (UI sans) — labels, chip, pips, footer
- Spectral Italic (serif) — example flavor line
Vendored under `cogs/vocabcatch_cog/fonts/`.

Rarity palette (accent `a` / deep `b`):
| Tier | a (accent) | b (deep) |
|------|-----------|----------|
| 1 Common | slate 148,163,184 | 100,116,139 |
| 2 Uncommon | emerald 52,211,153 | 16,185,129 |
| 3 Rare | blue 96,165,250 | 37,99,235 |
| 4 Epic | violet 192,132,252 | 147,51,234 |
| 5 Legendary | rainbow HSV sweep | (gold glow 251,191,36) |

## Build order

1. Schema + `VocabCatchMixin` + seed a small card set.
2. `renderer.py` — get a single premium card looking great (iterate on
   the image in isolation before wiring spawns).
3. `config.py` + spawn/catch `on_message` loop with the lock.
4. `$vocadex` collection + `$vocatchtop` leaderboard.
5. `$vocatchadmin` (force spawn, add card, stats).
6. Tests (pure: rarity weighting, accent-fold matching, points;
   renderer smoke; catch-race with fakes) + docs under `docs/cogs/`.

## Scope change v2 — bilingual, three channels

Made the game inclusive to both Spanish and English speakers. Three
spawn channels, each with a learner-direction **mode**:

- **Beginner-EN** (`en_to_es`) — shows the English word; catch by typing
  the Spanish word (English speakers learning Spanish).
- **Beginner-ES** (`es_to_en`) — shows the Spanish word; catch by typing
  the English word (Spanish speakers learning English).
- **General** (`show_es`) — shows the Spanish word; catch by typing it
  as shown (neutral).

Key changes from v1:
- Cards are **bidirectional**: `vocab_card_pool` now has `word_es`,
  `word_en`, `example_es`, `example_en` (dropped the single
  `word`/`translation`/`language`/`example`).
- `catch_logic.resolve_card(card, mode) -> CardView` turns a card into a
  one-directional view (prompt/answer/prompt_lang/answer_lang/example);
  the renderer takes `(card, view, *, revealed)` and shows a language
  badge + a "type the X word" hint.
- `answer_matches(guess, answer, *, answer_lang)` drops the leading
  article in the **answer** language (Spanish `el/la/...` or English
  `a/an/the`).
- **All channels spawn all rarities**, but with different weights:
  `BEGINNER_RARITY_WEIGHTS` (skews commoner) vs `GENERAL_RARITY_WEIGHTS`
  (steeper, more rares). No difficulty field — rarity *is* the
  difficulty knob, just weighted per channel.
- `main.py` tracks **per-channel** `ChannelState` (counter, cooldown,
  active spawn); each spawn carries its `mode` + resolved `view`.
- Config: `VOCATCH_BEGINNER_EN_CHANNEL_ID`,
  `VOCATCH_BEGINNER_ES_CHANNEL_ID`, `VOCATCH_GENERAL_CHANNEL_ID`
  (replaces the single `VOCATCH_CHANNEL_ID`).
