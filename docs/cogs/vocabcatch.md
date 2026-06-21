# Vocab Catch (`vocabcatch_cog`)

A Pokétwo-style "catch the card" minigame for **bilingual** vocab —
inclusive to both Spanish and English speakers. A premium Pillow-rendered
vocab card spawns in one of three channels; the first player to type
`catch <word>` claims it into their collection. Rarer cards spawn less
often and score more.

## Overview

Three spawn channels, each with a learner-direction **mode**:

| Channel | Mode | Card shows | Catch by typing | For |
|---------|------|-----------|-----------------|-----|
| Beginner-EN | `en_to_es` | the **English** word | the **Spanish** word | English speakers learning Spanish |
| Beginner-ES | `es_to_en` | the **Spanish** word | the **English** word | Spanish speakers learning English |
| General | `show_es` | the **Spanish** word | the **Spanish** word (as shown) | everyone (neutral) |

Cards are **bidirectional** — one shared pool, each card stores `word_es`
+ `word_en` (and an example per language). The channel mode picks which
side is the prompt (rendered) and which is the answer (typed). The card
art shows a language badge (`ESPAÑOL`/`ENGLISH`) and, while hidden, a
hint like *"catch — type the Spanish word"*.

An `on_message` listener in each configured channel counts non-bot
messages. Once a jittered threshold (`VOCATCH_SPAWN_EVERY ±
VOCATCH_SPAWN_JITTER`) is crossed **and** the per-channel cooldown
(`VOCATCH_SPAWN_COOLDOWN_S`) has elapsed, a card is chosen by that
channel's rarity weights and posted with the answer hidden. The first
player to type `catch <answer>` wins: the card is re-rendered revealed
(answer + example) and recorded. Unclaimed cards flee after
`VOCATCH_DESPAWN_S`.

Each channel tracks its **own** spawn state (one wild card at a time).
Spawn state lives in memory — a restart clears any pending card.

### Rarity per channel

All channels can spawn **all five rarities**, but with different weights:
beginner channels skew commoner (a Legendary is still possible, just
rarer); General uses a steeper curve so rares surface more often
(`BEGINNER_RARITY_WEIGHTS` vs `GENERAL_RARITY_WEIGHTS`).

### Catching

- Trigger: a bare `catch <word>` message (no bot prefix) in any spawn
  channel.
- The answer is the word in the channel's **answer language** (Spanish
  for Beginner-EN/General, English for Beginner-ES).
- Matching is **accent- and case-insensitive** and tolerates dropping a
  leading article in the answer language (Spanish `el/la/...` or English
  `a/an/the`): `catch nino`, `catch Niño`, `catch el niño` all catch
  Spanish `el niño`; `catch house` catches English `the house` (see
  `catch_logic.answer_matches`).
- **Race safety**: each spawn carries an `asyncio.Lock`; the winner is
  decided inside the lock so exactly one concurrent `catch` succeeds even
  if several land in the same tick. Wrong guesses are ignored silently.

### Duplicates & scoring

- Catching the same word again increments a per-user `count` (`×N`).
- Each catch is worth points by rarity (`RARITY_POINTS`,
  Common 1 → Legendary 25). The leaderboard ranks by total points.

## Card design

Premium "holo" collectible look (the locked **C+** design — see
[`../../plans/vocabcatch.md`](../../plans/vocabcatch.md)). Rendered with
Pillow in `renderer.py` following the house super-sample convention
([architecture](../architecture.md#image-rendering-pillow)): the whole
canvas is drawn at `S=4`, every coordinate scaled by `S`, then
LANCZOS-downsampled and exported as an **RGBA PNG** (transparent rounded
corners).

Card anatomy: rarity-tinted holographic frame (faint sheen + dot pattern
on the bright frame only — foil shines on light areas), a dark legible
content panel, a faded first-letter watermark for depth, a rarity name +
**language badge** (`ESPAÑOL`/`ENGLISH`) + 5-pip row, the prompt word in
Fraunces Black, a `gender · POS` chip, the answer (hidden until caught,
with a *"type the X word"* hint while hidden), and an italic example line
in the prompt language. Escalation: Common flat slate → Epic violet
(+ glow) → **Legendary rainbow rare** (multi-hue frame + corner
flourishes). The same card renders in either direction depending on the
channel mode (`renderer.render_card(card, view, revealed=...)`, where
`view` comes from `catch_logic.resolve_card`).

Fonts are vendored under `cogs/vocabcatch_cog/fonts/` (Fraunces, Sora,
Inter, Spectral Italic — all SIL OFL, with license files).

## Commands

### User-facing

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `catch <word>` | (No prefix.) Catch the active wild card by typing its word. | None | — |
| `$vocadex [@user]` | Show your (or another user's) collection: caught words, translations, duplicate counts, distinct/total/points footer. | None | 5s/user |
| `$vocatchtop` | Leaderboard of top collectors by points. | None | 10s/channel |

### Admin (`$vocatchadmin`, owner-only)

See [`../admin.md`](../admin.md#vocatchadmin-group-owner-only).

| Subcommand | Description |
|-----------|-------------|
| `$vocatchadmin seed` | Seed the starter card pool (no-op if the pool already has cards). |
| `$vocatchadmin spawn` | Force a spawn in the **current** channel (must be a configured game channel). |
| `$vocatchadmin addcard <1-5> "<word_es>" <word_en>` | Add a bidirectional card to the pool. |
| `$vocatchadmin preview <card_id> [mode]` | Render a card revealed in a mode (`show_es`/`en_to_es`/`es_to_en`) to preview the art. |
| `$vocatchadmin stats` | Active card count + configured channels and their modes. |

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `vocab_card_pool` | `VocabCatchMixin` (`db/vocab_catch.py`) | Curated shared word bank. **Bidirectional**: `word_es`, `word_en`, `part_of_speech`, `gender`, `example_es`, `example_en`, `rarity` (1-5), `active`. Distinct from per-user `vocab_notes`. |
| `vocab_card_catches` | `VocabCatchMixin` | Inventory; PK `(user_id, card_id)`, `count` increments on dupes. |

See [`../database.md`](../database.md#vocab-catch).

## Configuration & environment variables

| Constant / Env Var | Default | Purpose |
|--------------------|---------|---------|
| `VOCATCH_BEGINNER_EN_CHANNEL_ID` | 0 (disabled) | Beginner-EN channel (English prompt → Spanish answer). |
| `VOCATCH_BEGINNER_ES_CHANNEL_ID` | 0 (disabled) | Beginner-ES channel (Spanish prompt → English answer). |
| `VOCATCH_GENERAL_CHANNEL_ID` | 0 (disabled) | General channel (Spanish prompt → Spanish answer). |
| `VOCATCH_SPAWN_EVERY` | 25 | Messages between spawn checks (per channel). |
| `VOCATCH_SPAWN_JITTER` | 10 | ± random jitter on the threshold. |
| `VOCATCH_SPAWN_COOLDOWN_S` | 120 | Min seconds between spawns (per channel). |
| `VOCATCH_DESPAWN_S` | 300 | How long a wild card stays catchable. |
| `BEGINNER_RARITY_WEIGHTS` | 70/20/7/2/1 | Spawn odds per tier in beginner channels (`config.py`). |
| `GENERAL_RARITY_WEIGHTS` | 45/27/18/7/3 | Spawn odds per tier in the General channel (`config.py`). |
| `RARITY_POINTS` | 1/3/8/15/25 | Points per tier (`config.py`). |

## Known edge cases & gotchas

- **Catch race**: resolved via a per-spawn `asyncio.Lock`; exactly one
  concurrent correct `catch` wins, the rest no-op.
- **Empty pool**: `get_random_card` returns None and no card spawns
  (run `$vocatchadmin seed` first).
- **Per-channel state**: each channel has its own counter/cooldown/active
  card; a catch in one channel never affects another.
- **Rarity fallback**: if the weighted-chosen rarity has no active cards,
  the picker falls through the other rarities so a spawn never silently
  fails while cards exist.
- **Restart**: the in-memory wild card is lost — acceptable; the next
  threshold spawns a fresh one.
- **Hot-path errors**: rendering/DB calls in `on_message` are wrapped and
  logged; a failed catch DB write re-arms the spawn for a retry.
- **`get_font` reuse**: the renderer loads fonts directly at `size * S`
  (it does **not** reuse league's `get_font`), per the architecture
  gotcha.

## Testing & debugging

- `pytest tests/vocabcatch/` — pure logic (accent/article matching in
  both answer languages, mode resolution, per-channel weights, points),
  renderer smoke across all rarities/states/modes, and a concurrent
  catch-race test proving the single-winner lock plus per-mode answer
  routing.
- `$vocatchadmin preview <id> [mode]` renders a card in-channel to
  eyeball the art in any direction; `$vocatchadmin spawn` (run inside a
  game channel) forces an encounter.

## Related

- [`../../plans/vocabcatch.md`](../../plans/vocabcatch.md) — full design spec.
- [`../commands.md`](../commands.md) / [`../admin.md`](../admin.md) / [`../database.md`](../database.md).
