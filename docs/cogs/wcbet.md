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
Draw · 4.40 / 🇿🇦 South Africa · 8.50` → a stake select whose **option
labels carry the exact payout** (`500 → pays 4,250`, `All in (9,500) →
pays 80,750`). A running **bet slip** line summarizes the selection as
it fills in (`🧾 Bet slip: 500 on South Africa @ 8.50 → win 4,250`), and
the Place button is the final live preview (`Place 500 → win 4,250`);
while incomplete it states what's missing (`Place bet — pick an
outcome`). If the selected match already has a pending bet, the card
notes it will be replaced. `Custom amount…` is the only popup; it just
sets the stake and re-arms the panel — it never commits. Every step
re-validates kickoff server-side; a match that starts mid-flow drops out
and resets the selection. A **Close** button dismisses the panel; the
`My bets` view lists the user's bet history with **Back**/**Close**.

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

Each user has one bet per match, replaceable until kickoff — replacing
refunds the old stake and deducts the new one in a single DB
transaction. Group stage only for now; knockout rounds are deferred.

The fixture data is shared with `$wcfixtures` and `/wcpredict` —
`cogs/wcpredict_cog/fixtures.py` is the single source of truth (times
verified against FIFA/FOX; stored `match_id`s match FIFA's official
match numbers).

## Commands

### User-facing commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$wcbet` | Post the public betting prompt. | None | 5s/user |
| `$wcbettop` | Show the top 10 betting balances. | None | 10s/channel |
| `$wcbetme [@user]` | Show a betting profile card (balance+rank, net profit, W/L, win rate, biggest win, longest odds, streak). | None | 5s/user |
| `$wcbettest` | Identical flow; owner-only, retained for testing. | Owner-only | — |

### Panel buttons

The ephemeral panel offers **My bets**, **Share bets** (posts your open
singles + parlays publicly), **Parlay** (opens the parlay builder), and
**Close**.

### Parlays (accumulators)

The **Parlay** button opens a builder where you stake once on **2-5 legs**
(one outcome per match). Combined odds are the product of each leg's odds,
so payouts compound fast. All legs must win; the parlay loses the moment any
leg loses. Per-leg odds are snapshotted at placement. A voided match refunds
any parlay containing it (whole-parlay void). Parlay results announce to the
notification channel alongside single-bet results.

### Admin commands

See [`../admin.md`](../admin.md#wcbetadmin-group-owner-only) —
`$wcbetadmin result <match_id> <score>`, `$wcbetadmin void <match_id>`,
`$wcbetadmin stats` (owner-only, match-wide settlement).

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
| `wc_bet_bans` | `WCBetsMixin` | Users banned from betting (`user_id` PK); checked at panel entry, managed by `$wcbetmod`. |

See [`../database.md`](../database.md#world-cup-betting).

## Configuration & environment variables

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `WCBET_STARTING_BALANCE` | `cogs/wcbet_cog/config.py` | 10,000 | Coins granted on opt-in. |
| `WCBET_DAILY_ALLOWANCE` | `cogs/wcbet_cog/config.py` | 500 | Lazy daily top-up. |
| `WCBET_ODDS` | `cogs/wcbet_cog/config.py` | Decimal 1.5 | Fallback odds when no DraftKings line exists; payout math is `floor(stake × odds)` in `betting.payout`. |
| `WORLD_CUP_LOG_CHANNEL_ID` | `cogs/worldcup_cog/config.py` (re-exported as `WCBET_LOG_CHANNEL_ID`) | baked-in | Bet/settlement log channel, shared with all World Cup cogs. |
| `WCBET_AUTO_SETTLE` | env, read in `cogs/wcbet_cog/config.py` | 0 (propose) | 1 = poller settles bets itself; 0 = it only posts the command to run. |
| `WCBET_RESULTS_POLL_MINUTES` | env, read in `cogs/wcbet_cog/config.py` | 5 | Poll interval for the results loop. |

## Known edge cases & gotchas

- **Odds drift**: the Place button commits at re-resolved odds and
  refuses if the price moved from what it displayed (re-arms at the new
  price instead). Settlement always pays each bet's **stored** odds.
- **Odds-fetch blip**: if a bet armed at a real DraftKings price hits a
  failed re-fetch at placement, it is **not** repriced to the flat 1.5
  fallback. The armed price is kept for a retry and a `Place @ 1.5`
  button appears so the downgrade is an explicit user choice.
- **Kickoff race**: every panel step re-checks `bettable_fixtures(now)`;
  a commit after kickoff is rejected and the selection resets.
- **Replace semantics**: replacing a bet refunds the old stake *inside*
  the placement transaction — balance can legally exceed the displayed
  one mid-flight, never go negative.
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

## Testing & debugging

- `$wcbettest` — owner-only entrypoint, retained alongside the public
  `$wcbet` command for testing.
- Unit tests: `pytest tests/wcbet/` — pure logic (`test_betting.py`),
  ESPN parsing incl. odds (`test_results.py`), and panel/stepper
  behavior with fakes (`test_bet_panel.py`; the odds fetch is stubbed
  via the autouse `fake_odds` fixture).

## Related

- [`wcpredict.md`](./wcpredict.md) — champion predictions + fixtures data.
- [`../commands.md`](../commands.md) / [`../admin.md`](../admin.md).
- [`../database.md`](../database.md) — table reference.
