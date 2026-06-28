# World Cup Betting (`wcbet_cog`)

Virtual-coin betting on World Cup 2026 group-stage matches at **real
bookmaker odds** (DraftKings via ESPN): opt in for a starting balance,
bet on today's matches until kickoff, get paid `floor(stake × odds)` for
correct results. Results arrive via the ESPN poller or manual entry.

## Overview

`$wcbet` posts a public message with a single button. Anyone who clicks
it gets their **own ephemeral panel** — a Components V2
(`discord.ui.LayoutView`) stepper showing their balance, a step hint
(`Step 1 of 3 — pick a match`), and their pending bets. The flow is a
guided sequential chain: before a match is chosen it lists today's
bettable matches (with flags, localized `<t:…:t>` kickoff times, and the
current 1X2 odds line); once a match is selected that list **collapses
into a focused match card** so the same matches are never listed twice.
Pick a match → outcome buttons reprice to e.g. `🇲🇽 Mexico · 1.43 / 🤝
Draw · 4.40 / 🇿🇦 South Africa · 8.50` (knockout matches omit the Draw
button — they can't end in a draw) → a stake select whose **option
labels carry the exact payout** (`500 → pays 4,250`, `All in (9,500) →
pays 80,750`). If your balance is `0`, no stake options exist, so the
stake select is omitted and the Place button stays disarmed (rather
than rendering an empty select, which Discord rejects). A running **bet slip** line summarizes the selection as
it fills in (`🧾 Bet slip: 500 on South Africa @ 8.50 → win 4,250`), and
the Place button is the final live preview (`Place 500 → win 4,250`);
while incomplete it states what's missing (`Place bet — pick an
outcome`). If the selected match already has a pending bet, the card
notes it will be replaced. `Custom amount…` is the only popup; it just
sets the stake and re-arms the panel — it never commits. Every step
re-validates kickoff server-side; a match that starts mid-flow drops out
and resets the selection. A **Close** button dismisses the panel; the
timeout. The `My bets` view lists the user's bet history with **Back**/**Close**;
it shows the **latest `WCBET_MY_BETS_LIMIT` (20)** bets to stay within
Discord's 4,000-char Components V2 `TextDisplay` cap, with a
`use $wcbethistory` footer when older bets exist.

Odds are DraftKings close lines parsed from the same ESPN scoreboard
payload the results poller uses (`results.parse_event_odds` /
`match_odds`), cached in 10-minute buckets (`espn.fetch_match_odds`).
The odds at **placement** are snapshotted on the bet row and are what
settlement pays — later drift never changes an existing bet. Committing
re-resolves the price: if it moved from what the Place button displayed,
the click is refused with `Odds moved 4.40 → 4.20 — confirm again`. If
the bet was armed at a **real** line but the re-fetch returns nothing
(an ESPN blip), the panel does **not** silently downgrade to the flat
fallback — it keeps the armed price for a retry and surfaces an explicit
`Place @ 1.5` button so the user can consciously opt into the fallback
instead of being blocked. Matches with no published line (or a
persistent fetch failure) fall back to flat `WCBET_ODDS` (1.5) for all
three outcomes — never a mix of real and fallback legs. Payout math is
pure integer arithmetic (`stake * int(odds * 100) // 100`).

A configurable **house odds multiplier** (`$wcbetadmin multiplier`,
default 1.5x, stored in `bot_settings` as hundredths) scales every
offered line above ESPN's published price — applied to both real
DraftKings lines and the flat fallback at the display/arm boundary
(`espn.fetch_match_odds` / `results.apply_odds_multiplier` /
`_flat_odds`). Because the boosted price is what gets displayed, armed,
snapshotted, and paid, the snapshot/drift invariants below hold
unchanged. Changing the multiplier only affects **new** bets; existing
bets keep their locked-in odds. The raw ESPN prices stay cached
unscaled, so a multiplier change takes effect on the next render without
busting the odds cache.

Each user has one bet per match, replaceable until kickoff — replacing
refunds the old stake and deducts the new one in a single DB
transaction.

**Knockout rounds.** Group-stage fixtures have fixed teams and are always
bettable inside the 24h window. Knockout fixtures (Round of 32 onward)
ship with bracket placeholders ("Winner Group A", "Winner Match 73") and
are **not** bettable or settleable until their real teams are resolved.

Resolution is **automatic**: the results poller (and startup) calls
`espn.fetch_knockout_resolutions`, which reads ESPN's scheduled bracket
and matches each upcoming knockout fixture to its ESPN event by kickoff
time. When ESPN has decided **both** sides of a tie, the bot writes an
`auto`-sourced row to `wc_fixture_overrides` and applies it in memory, so
the match becomes bettable with no human action. Only fixtures within
`WCBET_KNOCKOUT_RESOLVE_LOOKAHEAD_DAYS` (default 3) are queried, so the
poller doesn't hammer ESPN for rounds weeks away.

An owner can still resolve or correct a pairing manually with
`$wcbetadmin setteam <match_id> <home> vs <away> [@ HH:MM]`. **Manual
overrides always win** — auto-resolution never overwrites a `manual` row
(tracked via the `source` column), so a hand-entered correction sticks
even if ESPN's data is stale or odd.

Resolutions persist and are re-applied on every startup (`WCBet.cog_load`),
so they survive restarts. `betting.bettable_fixtures` and
`results.fixtures_awaiting_result` both gate on `is_fixture_resolved`, and
ESPN settlement matches on the resolved `(kickoff, home, away)` — so team
names must match ESPN's (`results.TEAM_NAME_ALIASES` covers the few
spelling differences, e.g. Ivory Coast → Côte d'Ivoire).

**No draw on knockouts.** Knockout matches can't end in a draw — a level
score after extra time is decided on penalties. So once a knockout fixture
is selected, the betting panel (and the parlay builder) only offer **home /
away**, no draw button (`fixtures.is_knockout` gates this). Settlement uses
`betting.settle_outcome`, which for knockouts resolves to the side that
advanced: a decisive score wins outright, and a level score uses ESPN's
per-competitor `winner` flag (set on the shootout result). Group-stage
matches are unchanged — they still settle to home/draw/away off the score.

If a knockout ends level and ESPN hasn't reported the advancing side yet,
the auto-settler **defers** (logs a warning, settles nothing) rather than
recording a draw. To settle such a match manually, name the side that won
the shootout: `$wcbetadmin result <id> 1-1 pens home` (or `pens away`).

The fixture data is shared with `$wcfixtures` and `/wcpredict` —
`cogs/wcpredict_cog/fixtures.py` is the single source of truth (times
verified against FIFA/FOX; stored `match_id`s match FIFA's official
match numbers).

## Commands

### User-facing commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$wcbet` | Post the public betting prompt. | None | 5s/user |
| `$wcbettop` | Show the top 10 betting balances. Names render as `Server Nick (username)` resolved server-side (falls back to global username for members who left, then a bare ID only if the account is gone). | None | 10s/channel |
| `$wcbetme [@user]` | Show a betting profile card (balance+rank, net profit, W/L, win rate, biggest win, longest odds, streak). | None | 5s/user |
| `$wcbethistory [@user]` | Show recent wallet-event history from `wc_balance_log` for yourself or another member (allowances, bets, wins, refunds, resulting balance, relative timestamps). | `@user` (optional, defaults to you) | 5s/user |
| `$wcbetboard` | Show a public market board for currently bettable matches: odds, coins staked on home/draw/away, and bettor counts. Singles only; parlays excluded. | None | 10s/channel |
| `$wcbettest` | Identical flow; owner-only, retained for testing. | Owner-only | — |

### Panel buttons

The ephemeral panel offers **My bets**, **Manage** (edit/cancel pending
bets), **Parlay** (opens the parlay builder), **Share bets** (posts your
open singles + parlays publicly), and **Close**. The Place button sits on
its own row so the navigation row never exceeds Discord's five-button cap.

### Managing bets (edit / cancel)

**Manage** opens a view listing every pending **single** and **parlay**
in a select dropdown (singles 🎯, parlays 🎰). Picking one shows a focused
card with:

- **✏️ Edit** (singles only) — drops back into the normal match flow with
  that match pre-selected. Editing re-resolves odds at the **current**
  price (drift-guarded, same as a fresh placement) and replaces the bet
  via the existing place-or-replace transaction. Parlays have no Edit —
  cancel and rebuild instead.
- **❌ Cancel bet** — refunds the full stake and deletes the pending bet
  (`cancel_wc_bet`) or parlay + its legs (`cancel_wc_parlay`) in one
  transaction, logging a `bet_cancel` / `parlay_cancel` wallet event.
- **↩️ Back** — returns to the main panel.

Cancel is **free until kickoff**: every cancel re-checks
`bettable_fixtures(now)` server-side, so a single whose match has started
— or a parlay with *any* leg past kickoff — can no longer be cancelled
(its stake stays in play). A bet that was settled or voided between the
list render and the click surfaces a "no longer pending" notice instead
of double-refunding.

### Parlays (accumulators)

The **Parlay** button opens a builder where you stake once on **2-5 legs**
(one outcome per match). Combined odds are the product of each leg's odds,
so payouts compound fast. All legs must win; the parlay loses the moment any
leg loses. Per-leg odds are snapshotted at placement. A voided match refunds
any parlay containing it (whole-parlay void). Parlay results announce to the
notification channel alongside single-bet results.

To curb parlay-farming, each user may hold at most
`WCBET_MAX_PENDING_PARLAYS` (default **2**) pending parlays at once;
placing another while at the cap is rejected with a separate ephemeral
warning until one settles. The limit is enforced authoritatively inside the
`place_wc_parlay` transaction (a `COUNT` under the wallet's `FOR UPDATE`
lock), so concurrent places can't slip past it.

### Admin commands

See [`../admin.md`](../admin.md#wcbetadmin-group-owner-only) —
`$wcbetadmin result <match_id> <score> [pens home|away]`, `$wcbetadmin void <match_id>`,
`$wcbetadmin stats`, `$wcbetadmin multiplier [value]`, and
`$wcbetadmin setteam <match_id> <home> vs <away> [@ HH:MM]` (resolve a
knockout pairing) — owner-only, match-wide settlement + odds-boost +
knockout-team control.

### Moderator commands (`manage_messages`)

`$wcbetmod` (separate `mod.py`) is a per-user tier below the owner-only
admin group. All actions log to `#world-cup-log`. See
[`../admin.md`](../admin.md#wcbetmod-group-manage_messages).

| Command | Description |
|---------|-------------|
| `$wcbetmod user <@user>` | Read-only wallet/bet summary + ban status. |
| `$wcbetmod ban <@user> [reason]` / `unban` | Block/allow a user opening the panel. |
| `$wcbetmod give` / `take <@user> <amount>` | Adjust a balance (confirm prompt + loud log; cap 1,000,000; balance clamps ≥ 0). |

Match results and match-wide voids stay owner-only — they move everyone's
coins at once, too much blast radius for the mod tier.

## Flows

**Opt-in / daily allowance** (lazy, no scheduled task):

1. User clicks 🎰 on the public prompt.
2. If the user is **banned** (`wc_bet_bans`, set via `$wcbetmod ban`),
   they get an ephemeral refusal and no wallet is created.
3. No wallet → ephemeral opt-in panel; the button creates the wallet
   with 10,000 coins and swaps to the betting panel.
4. Wallet exists → a race-safe single `UPDATE … WHERE
   last_allowance_date IS DISTINCT FROM $today RETURNING balance` grants
   +5,000 once per UTC day; the panel shows a notice when it fires.

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
| `wc_bet_bans` | `WCBetsMixin` | Users banned from betting (`user_id` PK); checked at panel entry, managed by `$wcbetmod`. |
| `wc_fixture_overrides` | `WCBetsMixin` | Resolved knockout pairings (`match_id` PK; `home`, `away`, optional `time_et`, `source` = `manual`\|`auto`). Auto-filled from ESPN's bracket by the poller; `$wcbetadmin setteam` writes `manual` rows that auto-resolution never overwrites. Overlaid onto the static fixtures at startup. |

See [`../database.md`](../database.md#world-cup-betting).

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `WCBET_STARTING_BALANCE` | `cogs/wcbet_cog/config.py` | 10,000 | Coins granted on opt-in. |
| `WCBET_DAILY_ALLOWANCE` | `cogs/wcbet_cog/config.py` | 5,000 | Lazy daily top-up. |
| `WCBET_MAX_PENDING_PARLAYS` | `cogs/wcbet_cog/config.py` | 2 | Max unsettled parlays a user may hold at once (anti-farming). Enforced inside `place_wc_parlay`. |
| `WCBET_ODDS` | `cogs/wcbet_cog/config.py` | Decimal 1.5 | Fallback odds when no DraftKings line exists; payout math is `floor(stake × odds)` in `betting.payout`. (The house multiplier scales this too.) |
| Odds multiplier | `bot_settings` (`wcbet_odds_multiplier`, hundredths) via `$wcbetadmin multiplier` | 1.5 | House boost applied to every offered line (real + fallback). Set/reset at runtime; new bets only. |
| `WCBET_MY_BETS_LIMIT` | `cogs/wcbet_cog/config.py` | 20 | Max bets rendered in the panel's `My bets` view (Discord's `TextDisplay` is capped at 4,000 chars). Overflow points users at `$wcbethistory`. |
| `WORLD_CUP_LOG_CHANNEL_ID` | `cogs/worldcup_cog/config.py` (re-exported as `WCBET_LOG_CHANNEL_ID`) | baked-in | Bet/settlement log channel, shared with all World Cup cogs. |
| `WCBET_AUTO_SETTLE` | env, read in `cogs/wcbet_cog/config.py` | 0 (propose) | 1 = poller settles bets itself; 0 = it only posts the command to run. |
| `WCBET_RESULTS_POLL_MINUTES` | env, read in `cogs/wcbet_cog/config.py` | 5 | Poll interval for the results loop. |
| `WCBET_KNOCKOUT_RESOLVE_LOOKAHEAD_DAYS` | env, read in `cogs/wcbet_cog/config.py` | 3 | How many days ahead the poller looks when auto-resolving knockout teams from ESPN's bracket. A knockout becomes resolvable only within this horizon. |

## Known edge cases & gotchas

- **Odds drift**: the Place button commits at re-resolved odds and
  refuses if the price moved from what it displayed (re-arms at the new
  price instead). Settlement always pays each bet's **stored** odds.
- **Odds multiplier**: the house boost (`$wcbetadmin multiplier`) scales
  real lines *and* the flat fallback. It is read fresh on every panel
  refresh, the drift re-check, parlay legs, and the `$wcbetboard`, so all
  surfaces agree. Stored as hundredths in `bot_settings`; a value of 1
  disables the boost. Only new bets are affected — changing it never
  re-prices a placed bet.
- **Odds-fetch blip**: if a bet armed at a real DraftKings price hits a
  failed re-fetch at placement, it is **not** repriced to the flat 1.5
  fallback. The armed price is kept for a retry and a `Place @ 1.5`
  button appears so the downgrade is an explicit user choice.
- **Kickoff race**: every panel step re-checks `bettable_fixtures(now)`;
  a commit after kickoff is rejected and the selection resets.
- **Replace semantics**: replacing a bet refunds the old stake *inside*
  the placement transaction — balance can legally exceed the displayed
  one mid-flight, never go negative.
- **Cancel & odds-shopping (accepted)**: cancel refunds the full stake
  before kickoff, so in principle a user could place at one price, watch
  the line drift up, cancel, and re-bet at the better price for free.
  This is an accepted trade-off for a virtual-coin game — the friction is
  high, the "profit" doesn't cash out, and the natural **Edit** path is
  *not* exploitable (it re-resolves at the current drift-guarded price).
  The only real abuse — bailing on a bet once the match is underway — is
  closed by the server-side kickoff re-check on every cancel.
- **Timezones**: fixture times are ET = UTC−4 fixed (valid for the whole
  June–July window); `betting.kickoff_utc` converts to aware UTC. "Today"
  is the **ET** calendar date.
- **Ephemeral panels**: each clicker gets an independent panel; the
  public prompt button is intentionally **not** user-locked and stays
  reusable so several people can each open their own panel (unlike the
  one-shot `$wt` chooser). The panel has a **Close** button that
  collapses it to a short notice; otherwise it expires on the 600s
  timeout.
- **V2 constraints**: LayoutView messages cannot carry `content=`/embeds;
  the panel is view-only. The prompt message uses a classic `ui.View`.
- **My bets cap**: the `My bets` view renders only the latest
  `WCBET_MY_BETS_LIMIT` (20) bets. A heavy bettor's full history across
  the 72-match group stage (plus settled/replaced rows) would exceed
  Discord's 4,000-char `TextDisplay` limit and fail the whole panel
  render; `refresh()` over-fetches one row past the cap to detect
  overflow and append a `$wcbethistory` footer in a single query.

## Testing & debugging

- `$wcbettest` — owner-only entrypoint, retained alongside the public
  `$wcbet` command for testing.
- Unit tests: `pytest tests/wcbet/` — pure logic (`test_betting.py`),
  ESPN parsing incl. odds (`test_results.py`), and panel/stepper
  behavior with fakes (`test_bet_panel.py`; the odds fetch is stubbed
  via the autouse `fake_odds` fixture).
- `test_sql_guards.py` scans the `db/` SQL for Postgres-invalid patterns
  (e.g. `FOR UPDATE` with `DISTINCT`) that the fakes can't catch.
- `test_settlement_integration.py` exercises settlement/void against a
  **real** Postgres, including matches that have parlay legs. Skipped
  unless `TEST_DATABASE_URL` points at a throwaway database:
  `TEST_DATABASE_URL=postgresql://localhost/wcbet_test pytest tests/wcbet/test_settlement_integration.py`
  Or, with the Docker daemon running, one command spins up a throwaway
  Postgres, runs them, and tears it down:
  `python scripts/run_pg_integration_tests.py`

## Related

- [`wcpredict.md`](./wcpredict.md) — champion predictions + fixtures data.
- [`../commands.md`](../commands.md) / [`../admin.md`](../admin.md).
- [`../database.md`](../database.md) — table reference.
