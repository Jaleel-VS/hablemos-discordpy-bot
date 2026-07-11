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
| `WCPredictionsMixin` (`predictions.py`) | World Cup champion predictions |

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

### Stats tracking
- `channel_stats` — hourly per-channel message totals split by native-role
  type.
- Columns: `channel_id`, `role_type`, `hour_bucket`, `msg_count`.
- Purpose: powers `$stats`, `$stats report`, `$stats channels`,
  `$stats roles`, and `$stats heatmap`.
- `user_message_counts` — hourly per-user message totals for the stats
  cog leaderboard.
- Columns: `user_id`, `hour_bucket`, `msg_count`.
- Purpose: powers `$stats topusers`, active-user counts in `$stats report`,
  and messages-per-active-user calculations.
- `user_activity` — per-user first/last seen timestamps and latest
  native-role classification.
- Columns: `user_id`, `role_type`, `first_seen`, `last_seen`.
- Purpose: powers user growth, MAU, and new-user counts.
- Written by: `StatsCog.on_message` via `db.stats.StatsMixin
  .track_message_stats()`, which updates all stats tables in one
  transaction.

### Introductions / Exchange
- `introductions` — per-user intro post tracking.
- `exchange_posts` — active exchange posts, one per user, with repost
  cooldown timestamps and stored post data.

### Other
> TODO: document tables owned by `conversations`, `vocab`, `quotes`,
> `practice`, `interactions`, `tasks`, `dictation`, `notes`, `settings`
> mixins.

### World Cup predictions
- `wc_predictions` — one row per user (`user_id` PK). Stores the picked
  `Team X` role ID (`team_role_id`), a denormalized `team_name`
  snapshot, the owning `guild_id`, and `created_at` / `updated_at`.
  Indexed on `team_role_id` for distribution queries. The deadline
  (`wc_predict.deadline_ts`) and actual champion
  (`wc_predict.winner_role_id`) live in `bot_settings` rather than a
  dedicated table. See [`cogs/wcpredict.md`](./cogs/wcpredict.md).

### World Cup betting
- `wc_bet_wallets` — one row per opted-in user (`user_id` PK). Coin
  `balance` (starts at 10,000), `last_allowance_date` for the race-safe
  daily +5,000 claim, `guild_id`, timestamps.
- `wc_bets` — PK `(user_id, match_id)`: one editable bet per user per
  match. `outcome` (`home`/`draw`/`away`), `stake`, `odds` snapshot
  (NUMERIC), `status` (`pending`/`won`/`lost`/`void`), `payout`,
  `placed_at`/`settled_at`. Indexed on `(match_id, status)` for
  settlement. Balance changes and bet writes always share one
  transaction (`WCBetsMixin` in `db/bets.py`). A pending bet can be
  **cancelled** before kickoff (`cancel_wc_bet`): the row is deleted and
  the stake refunded in one transaction (logged `bet_cancel`). Pending
  parlays cancel the same way via `cancel_wc_parlay` (logged
  `parlay_cancel`).
- `wc_match_results` — one row per settled match (`match_id` PK):
  final score, derived outcome, `settled_at`. The insert doubles as the
  duplicate-settlement guard. See [`cogs/wcbet.md`](./cogs/wcbet.md).
- `wc_bet_bans` — one row per user banned from betting (`user_id` PK):
  `guild_id`, `banned_by`, optional `reason`, `created_at`. Checked at
  panel entry; managed by the `$wcbetmod` moderator group.
- `wc_fixture_overrides` — one row per resolved knockout pairing
  (`match_id` PK): `home`, `away`, optional `time_et`, `updated_at`.
  Written by `$wcbetadmin setteam`; overlaid onto the static fixture
  list at startup (`WCBet.cog_load`) and after each edit so knockout
  betting/settlement survive restarts. See [`cogs/wcbet.md`](./cogs/wcbet.md).

### Vocab Catch
- `vocab_card_pool` — curated, shared **bidirectional** word bank cards
  spawn from (`card_id` SERIAL PK): `word_es`, `word_en`,
  `part_of_speech`, `gender`, `example_es`, `example_en`, `rarity`
  (1-5), `active`. Indexed on `(active, rarity)` for weighted spawns.
  Distinct from the per-user `vocab_notes` table. The channel mode picks
  which language is the prompt vs. the catch answer.
  (`VocabCatchMixin` in `db/vocab_catch.py`.)
- `vocab_card_catches` — per-user inventory, PK `(user_id, card_id)`:
  `count` (increments on duplicate catches), `first_caught`/`last_caught`.
  Indexed on `user_id`. See [`cogs/vocabcatch.md`](./cogs/vocabcatch.md).

### Tickets
- `ticket_subscriptions` — mods opted in to new-ticket pings, PK
  `(user_id, guild_id)`: `created_at`. Indexed on `guild_id`. The
  `on_thread_create` listener loads this per guild and pings subscribers
  when a new ticket is opened. (`TicketSubsMixin` in `db/ticket_subs.py`.)
  See [`cogs/tickets.md`](./cogs/tickets.md).

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
