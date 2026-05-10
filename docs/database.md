# Database

PostgreSQL accessed via `asyncpg`. Everything goes through
`self.bot.db` (a shared `Database` instance) — never create your own
pool or acquire raw connections in cogs.

## Layout

```
db/
  __init__.py        Database class + DatabaseMixin base + pool helpers
  schema.py          initialize_schema(pool) — every CREATE TABLE + migration
  <domain>.py        One mixin per domain (query methods only)
```

The `Database` class composes every mixin via multiple inheritance.
Adding a new domain:

1. Create `db/<domain>.py` with a `<Domain>Mixin(DatabaseMixin)`.
2. Add tables to `db/schema.py` (use `CREATE TABLE IF NOT EXISTS` and
   `ADD COLUMN IF NOT EXISTS` so reruns are safe).
3. Import and add the mixin to the `Database` inheritance list in
   `db/__init__.py`.
4. Update this file.

## Mixin → domain map

| Mixin (file) | Owns |
|---|---|
| `NotesMixin` (`notes.py`) | User notes |
| `IntroductionsMixin` (`introductions.py`) | `/introduce` tracking |
| `ExchangePostsMixin` (`exchange_posts.py`) | Language-exchange post records |
| `SettingsMixin` (`settings.py`) | Bot-wide settings, disabled-cogs set |
| `ConversationsMixin` (`conversations.py`) | Conversation-starter tracking |
| `VocabMixin` (`vocab.py`) | Vocab / dictionary tracking |
| `LeaderboardMixin` (`leaderboard.py`) | Language League users, activity, rounds, exclusions |
| `QuotesMixin` (`quotes.py`) | Quote generator data |
| `PracticeMixin` (`practice.py`) | FSRS-based practice cards |
| `MetricsMixin` (`metrics.py`) | Command usage metrics (raw + daily rollup) |
| `InteractionsMixin` (`interactions.py`) | Per-user interaction tallies |
| `TasksMixin` (`tasks.py`) | Task / to-do persistence |
| `DictationMixin` (`dictation.py`) | Dictation puzzles & scores |
| `CrosswordMixin` (`crossword.py`) | Crossword games, participants, word events, active-game recovery |

## Key tables

### Language League
- `leaderboard_users` — opt-in state, learning languages, joined_at.
- `leaderboard_activity` — one row per counted message.
- `leaderboard_excluded_channels` — channels ignored by activity
  tracking.
- `leaderboard_rounds` — weekly round history.
- `leaderboard_round_recipients` — per-round role recipients (for
  cooldown logic).

### Crossword
- `crossword_words` — the word list (Spanish + English + clues +
  difficulty + theme).
- `crossword_scores` — **legacy flat-scores table. No longer written
  to.** Retained for historical reference. See below.
- `crossword_active_games` — one row per in-flight game (PK
  `channel_id`, carries `game_id`). Used for interrupt-recovery on
  restart.
- `crossword_games` — one row per completed/ended game. Carries
  `completion` ∈ {`completed`, `timeout`, `quit`, `interrupted`},
  `hints_used`, wall-clock times, elapsed seconds.
- `crossword_participants` — `(game_id, user_id)` with
  `words_solved`, `is_starter`. Starter always present even at 0.
- `crossword_word_events` — per-word data: `solved`, `solved_by`,
  `seconds_to_solve`, `had_hint`. Drives `$cwwords hardest|easiest|
  unseen`.

> **Migration note.** When the new crossword metrics schema landed, we
> stopped writing to `crossword_scores` but kept the table for history.
> `$cwstats` reads only the new tables. A "legacy" aggregate view could
> be added later if needed.

### Command metrics
- `command_metrics` — raw rows, one per command invocation.
- `metrics_daily` — daily rollup; upsert keyed on `(date,
  command_name)`. `cog_name` is collapsed with `MIN()` to avoid
  duplicate-conflict rows (see commit history for context).

### Introductions / Exchange
- `introductions` — per-user intro post tracking.
- `exchange_posts` — active exchange posts, one per user, with repost
  cooldown timestamps and stored post data.

### Other
> TODO: document tables owned by `conversations`, `vocab`, `quotes`,
> `practice`, `interactions`, `tasks`, `dictation`, `notes`, `settings`
> mixins.

## Querying conventions

- Use the `_fetch` / `_fetchrow` / `_fetchval` / `_execute` helpers
  from `DatabaseMixin`. They acquire from the pool for you.
- For multi-statement writes that must be atomic, acquire the
  connection and wrap in `async with conn.transaction():`.
- Use `$1`, `$2`, … positional parameters — never f-string SQL.
- `TIMESTAMPTZ` for new tables; legacy tables may be naive `TIMESTAMP`.
  See [`playbook.md`](./playbook.md) if time-filtered queries look
  off-by-hours.

## Migrations

There is no framework (Alembic, etc.). `schema.py` is the source of
truth and runs on every bot boot. Rules:

- `CREATE TABLE IF NOT EXISTS` for all new tables.
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for new columns.
- For destructive changes (drops, type changes), script them in
  `scripts/` and run manually against the target database; never bake
  destructive statements into `schema.py`.
