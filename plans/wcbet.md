# Plan: `$wcbet` — World Cup match betting (group stage)

Status: planned, not implemented.
Scope: group-stage fixtures only; results entered manually by admin. Live data is a later phase, out of scope here.

## Product decisions (locked with owner)

| Decision | Value |
|---|---|
| Entry | `$wcbet` prefix command → compact prompt with button → personal **ephemeral** Components V2 betting panel (in-place stepper, `$wt`-style) |
| Opt-in | Required; grants **10,000** coins once |
| Bet types | Match outcome only: home / draw / away |
| Odds | Flat **1.5x**, hardcoded constant (stored per-bet for future variable odds) |
| Payout | Stake deducted at bet time; correct bet credits `floor(stake * 1.5)` (net +0.5x). Lose → stake gone |
| Bets per match | One per user, replaceable until kickoff (replace = refund old stake, deduct new) |
| Match window | Only *today's* (ET) group-stage matches, selectable until kickoff |
| Settlement | Owner records score: `$wcbetadmin result <match_id> <home>-<away>`; outcome derived, all pending bets settled atomically |
| Broke users | Lazy daily allowance: **+500** on first `$wcbet` interaction of each UTC day |

## Architecture

```
cogs/wcbet_cog/
  __init__.py      — empty
  main.py          — WCBet(BaseCog): $wcbet command; setup() loads WCBet + WCBetAdmin
  admin.py         — WCBetAdmin(BaseCog): owner-only $wcbetadmin group
  config.py        — constants (odds, starting balance, allowance), log channel re-export
  betting.py       — PURE logic: kickoff times, today's-fixtures filter, outcome derivation, payout calc. No Discord/DB imports (mirrors scoring.py)
  views.py         — OpenBetPanelView (button prompt), BetPanelView(LayoutView) in-place stepper, StakeModal (single field)
db/bets.py         — WCBetsMixin (wallets, bets, results, settlement transaction)
tests/wcbet/       — pure-logic tests + panel/stake validation tests with fakes
```

---

## Phase 0 — Verified facts (done; cite these, do not re-derive)

### Fixture data verified against the real world (2026-06-11)

Web spot-checks (FOX, FIFA match centre, whensport, ESPN) against `cogs/wcpredict_cog/fixtures.py`:
- Match 1 Mexico–South Africa, Jun 11 → stored `15:00` ET = confirmed 3:00 PM ET (19:00 UTC) ✓
- Match 2 South Korea–Czechia, Jun 11 → stored `22:00` ET = confirmed 10:00 PM ET (FOX) ✓
- Match 13 Brazil–Morocco, Jun 13 → stored `18:00` ET = confirmed 6:00 PM EDT; FIFA match number 13 matches stored `match_id` ✓
- Match 10 Canada–Qatar, Jun 18 → stored `18:00` ET = confirmed 3:00 PM PT; FIFA match number 10 matches stored `match_id` ✓

Conclusion: `fixtures.py` is accurate (times AND match_ids align with FIFA's official numbering); ET = UTC−4 (EDT) is the correct fixed offset for the whole tournament window. **No fixture-correction work needed.** Trust `fixtures.py` as the single source of truth — `$wcbet`, `$wcfixtures`, and `/wcpredict` all share it.

### UX precedent: the `$wt` pattern (this is the model to copy)

`$whotalks`/`$wt` (`cogs/interactions_cog/main.py:201-256`) does: prefix command → small **button prompt** (`VisibilityView`, `cogs/utils/visibility.py`) → button click reveals a rich `LayoutView` built from `Container(TextDisplay, Separator, ..., accent_colour=...)` (`_build_wt_view`, `main.py:167-199`). Buttons drive the V2 component UI; nothing is crammed into one form. `$wcbet` follows the same shape, except the panel is ephemeral and interactive (selects/buttons rebuild it in place).

### Allowed discord.py 2.7.1 APIs (verified in `.venv/lib/python3.12/site-packages/discord/`)

- `ui.LayoutView(timeout=...)` — only view type that hosts V2 items (`ui/view.py:819-887`). Max 40 children total.
- `ui.Container(*children, accent_colour=..., ...)` (`ui/container.py:59-132`), `ui.TextDisplay(content)` (`ui/text_display.py:43-63`), `ui.Separator()` (`ui/separator.py:43-74`), `ui.ActionRow(*children)` — max 5 children, holds `Button`/`Select`; callbacks via `ActionRow.button(...)`/decorator stamping (`ui/action_row.py:79-155, 350-591`).
- `ui.Select(placeholder=..., options=[SelectOption(...)])` works inside an `ActionRow` in a `LayoutView` (`ui/select.py:418-521`).
- `interaction.response.edit_message(view=<LayoutView>)` — the in-place rebuild primitive (`interactions.py:1119-1231`).
- `ui.Modal(title=...)` (`ui/modal.py:62-135`) with `ui.Label(text, component)` wrapping `ui.TextInput(style=TextStyle.short)` (`ui/label.py:50-90`, `ui/text_input.py:53-123`) — used ONLY for the single stake field.
- Ephemeral interaction responses can carry LayoutViews; a no-timeout view sent ephemerally gets timeout forced to 15 min (`interactions.py:1015-1018`).
- V2 flag (`MessageFlags.components_v2`) is set automatically (`http.py:198-202`).

### Anti-patterns (verified to NOT work)

- `ui.View` + V2 items → raises (`ui/view.py:749-754, 785-790`). Use `LayoutView`. (`VisibilityView` is a classic `ui.View` with classic buttons — fine as-is.)
- V2 message with `content=`/`embed=`/`embeds=`/`poll=` → forbidden (`flags.py:547-552`). Panel messages are view-only.
- `TextInput(label="...")` → deprecated; wrap in `Label` (`ui/text_input.py:185-193`).
- `ActionRow` inside a `Modal` → deprecated (`ui/modal.py:231-235`).
- `row=` kwarg is ignored on V2 components.

### Repo conventions (verified)

- Cog auto-discovery: any `cogs/*_cog/main.py` is loaded (`cogs/utils/discovery.py:4-12`, `hablemos.py:66-72`). Extra cog classes loaded in `setup()` — copy `cogs/wcpredict_cog/main.py:251-253`.
- DB helpers: `DatabaseMixin._execute/_fetch/_fetchrow/_fetchval` (`db/__init__.py:12-32`); register new mixin in `Database` bases (`db/__init__.py:53-70`).
- Schema: idempotent blocks in `initialize_schema` — copy shape from `db/schema.py:740-753` (`wc_predictions`).
- Admin group skeleton: `cogs/wcpredict_cog/admin.py:67-221` (`@commands.group` + `@commands.is_owner()`, green/red/blue embeds from `cogs/utils/embeds.py`).
- Fixture data: `Fixture` TypedDict `{match_id, stage, group, date, time_et, home, away, venue, city}` (`cogs/wcpredict_cog/fixtures.py:18-29`); `GROUP_STAGE_FIXTURES` (`fixtures.py:725`); group-stage rows have no `"TBD"` times. Flags/labels: `TEAM_FLAGS` + `_team_label` in `cogs/wcpredict_cog/fixtures_view.py:18-67, 232-235`.
- Tests: handwritten fakes, no mocks (`tests/crossword/conftest.py:92-213`); `pytest.ini` has `asyncio_mode = auto`; `tests/test_smoke.py` auto-imports every cog + db mixin.
- Docs rule (`docs/CONTRIBUTING.md:11-21`): new command → `commands.md` + cog doc; admin command → `admin.md`; new tables → `database.md`.

---

## Phase 1 — Pure betting logic (`cogs/wcbet_cog/betting.py` + `config.py`)

No Discord, no DB imports. Everything here is unit-testable.

1. `config.py` — copy the shape of `cogs/wcpredict_cog/config.py`:
   - `WCBET_STARTING_BALANCE = 10_000`, `WCBET_DAILY_ALLOWANCE = 500`, `WCBET_ODDS = Decimal("1.5")` (or int basis points `150` — pick one and stick to it; payout must be deterministic integer math: `payout = stake * 3 // 2`).
   - Re-export `WCBET_LOG_CHANNEL_ID = WORLD_CUP_LOG_CHANNEL_ID` from `cogs.worldcup_cog.config` (same pattern as `cogs/wcpredict_cog/config.py:7,20`).
2. `betting.py`:
   - `ET_OFFSET = timezone(timedelta(hours=-4))` — fixed offset verified in Phase 0; do NOT pull in zoneinfo.
   - `kickoff_utc(fixture: Fixture) -> datetime` — parse `date` + `time_et`, attach ET offset, convert to UTC. Raise/skip on `"TBD"` (defensive; group stage has none).
   - `bettable_fixtures(now_utc: datetime) -> list[Fixture]` — group-stage fixtures whose ET date == today's ET date and `kickoff_utc > now_utc`.
   - `Outcome = Literal["home", "draw", "away"]`; `outcome_from_score(home: int, away: int) -> Outcome`.
   - `payout(stake: int) -> int` — integer math, documented rounding (floor).
   - `parse_score(raw: str) -> tuple[int, int] | None` — accepts `2-1`, `2:1`, `2 1`; bounds-checked (AGENTS.md: parsers never crash on user input).
   - `parse_stake(raw: str, balance: int) -> int | None` — int parse, `1 ≤ stake ≤ balance`, supports `all`.

**Verification:** Phase 5 unit tests cover every function; until then `python -c "from cogs.wcbet_cog import betting"` imports cleanly.
**Anti-patterns:** no `datetime.now()` inside pure functions — `now_utc` is always a parameter (testability).

## Phase 2 — DB layer (`db/bets.py`, `db/schema.py`, `db/__init__.py`)

1. Schema blocks appended in `initialize_schema` (copy idempotent shape from `db/schema.py:740-753`):
   ```sql
   CREATE TABLE IF NOT EXISTS wc_bet_wallets (
       user_id             BIGINT PRIMARY KEY,
       guild_id            BIGINT NOT NULL,
       balance             BIGINT NOT NULL,
       last_allowance_date DATE,
       created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
   );
   CREATE TABLE IF NOT EXISTS wc_bets (
       user_id    BIGINT NOT NULL REFERENCES wc_bet_wallets(user_id),
       match_id   INTEGER NOT NULL,
       guild_id   BIGINT NOT NULL,
       outcome    TEXT NOT NULL CHECK (outcome IN ('home','draw','away')),
       stake      INTEGER NOT NULL CHECK (stake > 0),
       odds       NUMERIC(5,2) NOT NULL,
       status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','won','lost','void')),
       payout     INTEGER,
       placed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       settled_at TIMESTAMPTZ,
       PRIMARY KEY (user_id, match_id)
   );
   CREATE INDEX IF NOT EXISTS idx_wc_bets_match_status ON wc_bets(match_id, status);
   CREATE TABLE IF NOT EXISTS wc_match_results (
       match_id   INTEGER PRIMARY KEY,
       home_score INTEGER NOT NULL,
       away_score INTEGER NOT NULL,
       outcome    TEXT NOT NULL,
       settled_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
   );
   ```
2. `db/bets.py` — `class WCBetsMixin(DatabaseMixin)`; register in `Database` bases (`db/__init__.py:53-70`). Methods:
   - `get_wc_wallet(user_id)` / `create_wc_wallet(user_id, guild_id, starting_balance)` (INSERT ... ON CONFLICT DO NOTHING; return bool created)
   - `claim_wc_daily_allowance(user_id, amount, today: date) -> int | None` — single UPDATE with `WHERE last_allowance_date IS DISTINCT FROM $today` returning new balance; None if already claimed. Race-safe by construction.
   - `place_wc_bet(user_id, guild_id, match_id, outcome, stake, odds) -> int` — **one transaction** (`async with self.pool.acquire() as conn, conn.transaction():`): refund existing pending bet on this match if any, check balance ≥ stake (raise domain error if not), deduct, upsert bet. Returns new balance. Transactions are allowed inside mixins — the "no raw SQL in cogs" rule applies to cogs only.
   - `get_wc_user_bets(user_id, status=None) -> list`
   - `settle_wc_match(match_id, home_score, away_score, outcome, payouts: dict[int, int]) -> dict` — one transaction: insert `wc_match_results` (reject duplicate), select pending bets `FOR UPDATE`, mark won/lost, credit winners' wallets, return summary `{winners, losers, total_paid}`. Payout amounts precomputed by the cog via `betting.payout` (keep multiplier math in Python, not SQL).
   - `void_wc_match(match_id) -> dict` — refund all pending stakes, mark `void` (postponements).
   - `wc_bet_stats(guild_id)` — opted-in count, pending bet count, total staked.

**Verification:** `pytest tests/test_smoke.py` (auto-imports the new mixin); bot boot creates tables idempotently.
**Anti-patterns:** no balance mutation outside a transaction that also touches `wc_bets`; never compute payout in SQL.

## Phase 3 — UI (`cogs/wcbet_cog/views.py`) — `$wt`-style stepper

Copy the `$wt` shape: command → button prompt → rich V2 panel. The panel is **ephemeral and per-user**, and its buttons/selects rebuild it in place via `interaction.response.edit_message(view=...)`.

1. `OpenBetPanelView(ui.View)` — classic view, public prompt (analogous to `VisibilityView`, `cogs/utils/visibility.py`):
   - Single `[Make prediction 🎰]` button, NOT user-locked — anyone clicks, gets their *own* ephemeral panel.
   - Callback: fetch/clicker's wallet; lazily claim daily allowance (+500, once per UTC day); build `BetPanelView` for that user; `interaction.response.send_message(view=panel, ephemeral=True)`.
   - Not opted in → ephemeral opt-in panel instead (explainer `TextDisplay` + `[Opt in — get 10,000 coins]` button; on click create wallet then swap in the betting panel via `edit_message`).
   - Timeout 600s → disable button, like `VisibilityView.on_timeout` (`visibility.py:60-63`).
2. `BetPanelView(ui.LayoutView)` — the personal stepper; holds state `(user_id, balance, selected_match_id, selected_outcome)` and is rebuilt on every step:
   - `Container(accent_colour=Color.blurple())` — copy composition style from `_build_wt_view` (`cogs/interactions_cog/main.py:186-198`):
     - `TextDisplay`: `## World Cup betting` + balance + pending-bet count.
     - `Separator`
     - `TextDisplay`: today's bettable matches with flags (`TEAM_FLAGS` via import from `cogs/wcpredict_cog/fixtures_view.py`) and `<t:…:t>` kickoff timestamps; existing bet per match shown inline (`-# you have 500 on Draw`).
     - `Separator`
     - `ActionRow(ui.Select)` — "Choose a match…" (today's bettable; ≤6 options/day). Selecting → rebuild panel with match highlighted.
     - `ActionRow` — outcome buttons `[🏠 Home]` `[🤝 Draw]` `[✈️ Away]`, disabled until a match is selected; selected one rendered `ButtonStyle.success`. Clicking → rebuild.
     - `ActionRow` — `[Place bet…]` (enabled once match+outcome chosen; opens `StakeModal`) + `[My bets]` (rebuilds panel showing full bet history section).
   - Every callback re-validates against `bettable_fixtures(now_utc)` — a match that kicked off mid-flow disappears and selection resets with a notice line.
   - `interaction_check`: only the owning user (panel is ephemeral anyway — defense in depth).
   - Timeout ≤ 900s (ephemeral cap).
3. `StakeModal(ui.Modal, title="Stake")` — single field: `Label("Coins to bet", ui.TextInput(style=TextStyle.short, placeholder="e.g. 500 — or 'all'"))`.
   - `on_submit`: `parse_stake`; re-check match still bettable; call `place_wc_bet` (transaction enforces balance); edit the panel in place to show the placed bet + new balance. Domain errors → friendly notice rendered into the panel, never raw exceptions (AGENTS.md).
4. Log placed bets + settlements to `WCBET_LOG_CHANNEL_ID` — copy `_get_log_channel`/`_log_pick` shape from `cogs/wcpredict_cog/views.py:216-252` with `Forbidden`/`HTTPException` handling.

**Verification:** manual smoke on test guild — `$wcbet` → prompt → opt-in path; select match → outcome → stake; re-bet same match (old stake refunded); panel select excludes started matches; two users clicking the same prompt get independent panels.
**Anti-patterns:** no `content=` alongside a LayoutView; no V2 items inside `OpenBetPanelView` (classic `ui.View`); no `TextInput(label=)`; callbacks never trust client state — kickoff/balance re-checked server-side on every step.

## Phase 4 — Cog + admin (`main.py`, `admin.py`)

1. `main.py` — `WCBet(BaseCog)`:
   - `@commands.command(name="wcbet")` + `@commands.cooldown(1, 5, commands.BucketType.user)` (copy `cogs/wcpredict_cog/main.py:235-248`).
   - Guild-only check. Sends the compact `OpenBetPanelView` prompt (pattern: `cogs/interactions_cog/main.py:254-255`).
   - `setup()` loads `WCBet` + `WCBetAdmin` (copy `main.py:251-253`).
2. `admin.py` — `WCBetAdmin(BaseCog)`, owner-only `@commands.group(name="wcbetadmin")` (copy skeleton `cogs/wcpredict_cog/admin.py:67-221`):
   - `result <match_id> <score>` — validate match is group-stage and exists (`FIXTURE_BY_ID`), `parse_score`, derive outcome, compute payouts via `betting.payout`, call `settle_wc_match`, green embed summary (N won / M lost / X coins paid), log to channel.
   - `void <match_id>` — refund pending stakes.
   - `stats` — wallet count, pending bets, total staked, biggest balance.
   - Reject DM use for guild-scoped subcommands (copy `admin.py:127-129`).

**Verification:** `pytest tests/test_smoke.py` imports both cogs; manual: settle a fake past match, confirm winner balance = old + floor(stake*1.5), loser unchanged, duplicate `result` rejected.
**Anti-patterns:** no raw SQL in cog files; no `tree.sync()` anywhere (prefix-only feature); no hardcoded channel IDs in cog files.

## Phase 5 — Tests (`tests/wcbet/`)

Conventions: handwritten fakes, `asyncio_mode=auto`, frozen `now_utc` parameters (copy harness style from `tests/crossword/conftest.py:92-213`).

- `test_betting.py` (pure, no fakes needed):
  - `kickoff_utc`: ET→UTC conversion correct (22:00 ET → 02:00 UTC next day edge — real case, match 2).
  - `bettable_fixtures`: filters by ET-date and excludes started matches; ET-midnight boundary case.
  - `outcome_from_score`: home/draw/away; `parse_score`: valid forms, garbage, negatives, empty.
  - `payout`: odd stakes floor correctly (e.g. 101 → 151); `parse_stake`: non-numeric, zero, negative, > balance, `all`.
- `test_bet_panel.py` (FakeDB recording calls, fake Interaction):
  - stake submit with invalid input → rejected, no DB call.
  - match kicked off between panel open and stake submit → rejected.
  - valid flow calls `place_wc_bet` with parsed args.
  - outcome buttons disabled until match selected (assert built view state).

**Verification:** `pytest tests/wcbet/ tests/test_smoke.py` green; `ruff check` clean.

## Phase 6 — Docs & cleanup (gated on Phases 1-5 working)

Per `docs/CONTRIBUTING.md:11-21`:
- `docs/commands.md` — `$wcbet` entry.
- `docs/admin.md` — `$wcbetadmin` group.
- `docs/database.md` — three new tables.
- `docs/cogs/` — new `wcbet.md` cog doc; mention in `docs/README.md` if the index lists cogs.
- Conventional commit(s): `feat(wcbet): ...`.

## Final verification checklist

- [ ] `ruff check` clean
- [ ] `pytest` (full suite) green — smoke test imports new cog + mixin
- [ ] Bot boots locally; schema blocks idempotent on second boot
- [ ] Manual flow on test guild: opt-in → 10,000; bet → balance drops; re-bet same match → old stake refunded; bet after kickoff blocked; `result` pays floor(stake×1.5); duplicate `result` rejected; daily allowance claims once per UTC day; two simultaneous users get independent panels
- [ ] grep guards: no `TextInput(label=`, no V2 items in plain `ui.View`, no `pool.acquire` in `cogs/wcbet_cog/`, no `os.getenv` outside config helpers

## Deferred (explicitly out of scope)

- Live score ingestion / auto-settlement
- Knockout-stage betting (TBD kickoff times need handling)
- Variable odds (schema already stores per-bet odds snapshot)
- Betting leaderboard command (`wc_bet_wallets` ordered by balance — trivial later)
