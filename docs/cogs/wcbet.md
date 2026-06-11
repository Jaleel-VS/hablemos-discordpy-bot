# World Cup Betting (`wcbet_cog`)

Virtual-coin betting on World Cup 2026 group-stage matches: opt in for a
starting balance, bet on today's matches until kickoff, get paid 1.5x
for correct results. Settlement is manual (owner records scores).

## Overview

`$wcbet` posts a public message with a single button. Anyone who clicks
it gets their **own ephemeral panel** — a Components V2
(`discord.ui.LayoutView`) stepper showing their balance, today's
bettable matches (with flags and localized `<t:…:t>` kickoff times), and
their pending bets. The flow is: select a match → pick 🏠 Home / 🤝 Draw
/ ✈️ Away → "Place bet…" opens a one-field stake modal. Every step
re-validates kickoff server-side; a match that starts mid-flow drops out
of the panel and resets the selection.

Betting is win/lose/draw only with flat hardcoded odds (1.5x). Stakes
are deducted when the bet is placed; a correct bet credits
`floor(stake × 1.5)` back (net +0.5x). Each user has one bet per match,
replaceable until kickoff — replacing refunds the old stake and deducts
the new one in a single DB transaction. Group stage only for now;
knockout rounds and live data are deferred.

The fixture data is shared with `$wcfixtures` and `/wcpredict` —
`cogs/wcpredict_cog/fixtures.py` is the single source of truth (times
verified against FIFA/FOX; stored `match_id`s match FIFA's official
match numbers).

## Commands

### User-facing commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$wcbet` | Post the public betting prompt. **Currently disabled** (commented out in `main.py`) pending testing. | None | 5s/user (when enabled) |
| `$wcbettest` | Identical flow, live now for pre-release testing. | Owner-only | — |

### Admin commands

See [`../admin.md`](../admin.md#wcbetadmin-group-owner-only) —
`$wcbetadmin result <match_id> <score>`, `$wcbetadmin void <match_id>`,
`$wcbetadmin stats`.

## Flows

**Opt-in / daily allowance** (lazy, no scheduled task):

1. User clicks 🎰 on the public prompt.
2. No wallet → ephemeral opt-in panel; the button creates the wallet
   with 10,000 coins and swaps to the betting panel.
3. Wallet exists → a race-safe single `UPDATE … WHERE
   last_allowance_date IS DISTINCT FROM $today RETURNING balance` grants
   +500 once per UTC day; the panel shows a notice when it fires.

**Settlement** — manual command or the ESPN results poller:

1. `$wcbetadmin result 1 2-1` → score parsed (`2-1` / `2:1` / `2 1`),
   outcome derived (`home`).
2. One transaction: result row inserted (duplicate ⇒ rejected), pending
   bets locked `FOR UPDATE`, winners credited `payout(stake)`, statuses
   flipped to `won`/`lost`.
3. Summary embed in the invoking channel + log to `#world-cup-log`.

**Results poller** (`tasks.loop`, every `WCBET_RESULTS_POLL_MINUTES`):

1. Skips entirely unless an unsettled group-stage match is inside its
   post-kickoff window (kickoff → +6h), so idle traffic is zero.
2. Fetches ESPN's free, key-less scoreboard JSON
   (`site.api.espn.com/...scoreboard?dates=YYYYMMDD` — the `dates` param
   uses the ET calendar date, same convention as `fixtures.py`).
3. Completed events are mapped to our `match_id` by exact
   `(kickoff UTC, home, away)` after normalizing five team-name
   spellings (`results.TEAM_NAME_ALIASES`) — a mismatch can never settle
   the wrong match; it just doesn't match.
4. Default **propose mode**: posts the finished score + ready-to-run
   `$wcbetadmin result …` command to `#world-cup-log` (once per match
   per process). With `WCBET_AUTO_SETTLE=1` it settles directly through
   the same transaction as the manual command and announces a summary;
   a manual settlement racing it simply wins (duplicate guard).

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `wc_bet_wallets` | `WCBetsMixin` (`db/bets.py`) | Per-user coin balance + `last_allowance_date`. |
| `wc_bets` | `WCBetsMixin` | PK `(user_id, match_id)`; outcome, stake, odds snapshot, status, payout. |
| `wc_match_results` | `WCBetsMixin` | Final score per settled match; doubles as the duplicate-settlement guard. |

See [`../database.md`](../database.md#world-cup-betting).

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `WCBET_STARTING_BALANCE` | `cogs/wcbet_cog/config.py` | 10,000 | Coins granted on opt-in. |
| `WCBET_DAILY_ALLOWANCE` | `cogs/wcbet_cog/config.py` | 500 | Lazy daily top-up. |
| `WCBET_ODDS` | `cogs/wcbet_cog/config.py` | 1.5 | Display/odds snapshot; payout math is integer `stake * 3 // 2` in `betting.py`. |
| `WORLD_CUP_LOG_CHANNEL_ID` | `cogs/worldcup_cog/config.py` (re-exported as `WCBET_LOG_CHANNEL_ID`) | baked-in | Bet/settlement log channel, shared with all World Cup cogs. |
| `WCBET_AUTO_SETTLE` | env, read in `cogs/wcbet_cog/config.py` | 0 (propose) | 1 = poller settles bets itself; 0 = it only posts the command to run. |
| `WCBET_RESULTS_POLL_MINUTES` | env, read in `cogs/wcbet_cog/config.py` | 5 | Poll interval for the results loop. |

## Known edge cases & gotchas

- **Kickoff race**: the stake modal can sit open past kickoff; `on_submit`
  re-checks `bettable_fixtures(now)` and rejects with a notice.
- **Replace semantics**: replacing a bet refunds the old stake *inside*
  the placement transaction — balance can legally exceed the displayed
  one mid-flight, never go negative.
- **Timezones**: fixture times are ET = UTC−4 fixed (valid for the whole
  June–July window); `betting.kickoff_utc` converts to aware UTC. "Today"
  is the **ET** calendar date.
- **Ephemeral panels**: each clicker gets an independent panel; the
  public prompt button is intentionally not user-locked.
- **V2 constraints**: LayoutView messages cannot carry `content=`/embeds;
  the panel is view-only. The prompt message uses a classic `ui.View`.

## Testing & debugging

- `$wcbettest` — owner-only entrypoint while the public command is
  gated. To go live: uncomment the `$wcbet` block in
  `cogs/wcbet_cog/main.py` (and optionally remove `wcbettest`).
- Unit tests: `pytest tests/wcbet/` — pure logic (`test_betting.py`)
  and panel/modal behavior with fakes (`test_bet_panel.py`).

## Related

- [`wcpredict.md`](./wcpredict.md) — champion predictions + fixtures data.
- [`../commands.md`](../commands.md) / [`../admin.md`](../admin.md).
- [`../database.md`](../database.md) — table reference.
