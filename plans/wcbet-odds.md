# Plan: realistic odds for `$wcbet` (DraftKings via ESPN)

Status: planned, not implemented. Builds on the shipped wcbet feature
(`plans/wcbet.md`) — schema and bet flow already anticipate this.

## Why this is cheap

- `wc_bets.odds NUMERIC(5,2)` already snapshots odds per bet — **no migration**.
- The ESPN scoreboard endpoint the results poller already uses carries
  DraftKings odds. **No new API, key, or quota.**
- Settlement already pays from a `payout_fn` — only its signature widens.

## Verified source facts (live-checked 2026-06-11)

Same endpoint: `site.api.espn.com/.../scoreboard?dates=YYYYMMDD`.
Per event: `competitions[0].odds[0]` (provider DraftKings, `priority: 1`):

- Home ML: `odds[0]["moneyline"]["home"]["close"]["odds"]` → `"-235"` (string, signed American)
- Away ML: `odds[0]["moneyline"]["away"]["close"]["odds"]` → `"+750"`
- Draw ML: `odds[0]["drawOdds"]["moneyLine"]` → `340` (number, no sign)
- `open` variants exist alongside `close`; use `close` (current line), fall back to `open` if `close` missing.

Live example (match 1): Mexico −235 / Draw +340 / South Africa +750
→ decimal **1.43 / 4.40 / 8.50**.

American → decimal conversion (exact, `Decimal` math, 2dp ROUND_HALF_UP):
`ml < 0 → 1 + 100/|ml|`; `ml > 0 → 1 + ml/100`. NUMERIC(5,2) caps at
999.99 — no realistic soccer line exceeds it.

## Product decisions (proposed — confirm before /do)

| Decision | Value |
|---|---|
| Odds basis | DraftKings close line at **bet placement time** (snapshot = what you're paid; later drift doesn't change your bet — standard bookmaker behavior) |
| Granularity | All-or-nothing per match: if any of home/draw/away is unavailable, ALL three fall back to flat 1.5 (mixed real/fallback would misprice the missing leg) |
| Fallback | `WCBET_ODDS = 1.5` keeps its role as the fallback constant |
| Existing pending bets | Untouched — they pay their stored 1.5 snapshot |
| Payout math | `floor(stake × odds)` in integer arithmetic: `stake * odds_hundredths // 100` |
| Freshness | 10-minute cache buckets; odds re-resolved at modal submit (the bet records what was current at submit, and the confirmation notice states it) |

## Phase 1 — Pure logic (`results.py` + `betting.py`)

`results.py` is already the ESPN-parsing module (aliases + event matching live there) — extend it, no new module:

1. `MatchOdds = TypedDict("MatchOdds", {"home": Decimal, "draw": Decimal, "away": Decimal})`
2. `american_to_decimal(ml: int) -> Decimal` — exact Decimal math, quantize `0.01`.
3. `parse_event_odds(event: dict) -> MatchOdds | None` — bounds-checked like `_parse_event`; requires all three legs (close, falling back to open); None on anything missing/malformed.
4. `match_odds(payload: dict, fixtures: list[Fixture]) -> dict[int, MatchOdds]` — reuses the existing `(kickoff_utc, home, away)` index + `TEAM_NAME_ALIASES`. Refactor the small index-building block shared with `match_results` into a helper.

`betting.py`:

5. `payout(stake: int, odds: Decimal) -> int` — `stake * int(odds * 100) // 100`. (Breaking change: update ALL callers — admin settle, poller auto-settle, views' potential-payout display, tests. `lsp references payout` first.)

## Phase 2 — Plumbing

1. `db/bets.py settle_wc_match`: `payout_fn: Callable[[int], int]` → `Callable[[int, Decimal], int]`, called as `payout_fn(bet["stake"], bet["odds"])` (asyncpg returns NUMERIC as Decimal already).
2. `admin.py result` + `main.py _handle_result` (auto mode): pass `betting.payout` unchanged — signature now matches.
3. Odds fetcher (in `views.py` or `main.py`, networked side):
   ```python
   @async_cache(maxsize=8)
   async def _fetch_odds(date_str: str, bucket: int) -> dict[int, MatchOdds]
   ```
   `bucket = int(now.timestamp()) // 600` gives 10-min TTL on top of the
   existing `cogs/utils/async_cache.py` (LRU has no TTL; the bucket key
   provides it). Failure → `{}` → flat fallback, panel still works.

## Phase 3 — UI (`views.py`) — in-panel stake step, popup demoted

Owner decision (2026-06-11): no stake popup on the main path. Modals
cannot live-update (TextInput reports only on submit — platform limit),
so the stake step moves into the panel where every click re-renders.
The whole flow is sequential chaining: match → outcome → stake →
confirm, all in the ephemeral LayoutView.

1. `BetPanelView.refresh()` also resolves `self._odds: dict[int, MatchOdds]`
   and tracks new state `selected_stake: int | None` (cleared whenever
   match or outcome changes).
2. Outcome buttons gain the price: `🇲🇽 Mexico · 1.43` / `🤝 Draw · 4.40`
   / `🇿🇦 South Africa · 8.50` (flat fallback renders `· 1.5` so pricing
   is always explicit). Match list lines show the triple compactly:
   `-# 1.43 / 4.40 / 8.50`.
3. **Stake select** (new ActionRow between outcomes and the confirm row),
   disabled with placeholder `Pick an outcome first` until match+outcome
   are chosen. Options are precomputed against the selected outcome's
   odds — the live preview lives in the option labels themselves:
   - presets `100 / 250 / 500 / 1,000 / 2,500 / 5,000` filtered to
     `<= balance`, each labelled `500 → pays 1,800`
   - `All in (9,500) → pays 34,200`
   - `Custom amount…` → opens the single-field `StakeModal`; on submit it
     does NOT commit — it sets `selected_stake` and re-renders the panel
     (same preview path as presets; one extra click to place).
4. **Place button is the final preview**: disabled until stake chosen,
   then labelled `Place 500 → win 1,800`. Clicking it commits: re-resolve
   odds (cached); if the price drifted from what the button displayed,
   do NOT commit — re-render with notice `Odds moved 4.40 → 4.20 —
   confirm again at the new price` (bookmaker-style). Otherwise
   `place_wc_bet(..., odds=...)`, success notice
   `500 on 🇿🇦 South Africa @ 8.50 — pays 4,250 if it lands`, stake
   state cleared.
5. Changing outcome/match after picking a stake re-renders every payout
   number against the new odds (stake kept if still `<= balance`, else
   cleared) — this is the "live" recompute.
6. History lines: `**500** @ 4.40 on **Draw**`.

Component budget check: container children = header TextDisplay,
Separator, matches TextDisplay, Separator, match-select row, outcome row,
stake-select row, confirm row = 8 — far under the 40-item cap; rows hold
≤5 items each.

## Phase 4 — Tests + docs

- `test_results.py`: `american_to_decimal` (−235→1.43, +750→8.50, +340→4.40, −100→2.00); `parse_event_odds` close/open fallback + each missing-leg case → None; `match_odds` alias + mismatch cases. Reuse `_espn_event` builder, extended with an odds block.
- `test_betting.py`: `payout` with Decimal odds incl. flooring (`payout(101, Decimal("1.50")) == 151`, `payout(3, Decimal("4.40")) == 13`); new pure helper `stake_presets(balance) -> list[int]` (presets + all-in filtering, balance 0/small/huge cases).
- `test_bet_panel.py`: stake select disabled until outcome chosen; option labels carry payouts; preset pick arms the Place button with live label; custom modal arms (does not commit); place commits with resolved odds; outcome change re-prices and keeps/clears stake correctly; odds-fetch failure → flat 1.5 everywhere.
- Docs: `docs/cogs/wcbet.md` (odds section, decision table, new flow), `docs/commands.md` blurb tweak.

## Anti-pattern guards

- NEVER float math for money: Decimal in, integer coins out.
- NEVER trust panel-render odds at submit — re-resolve.
- NEVER partial-fallback a match's legs.
- Settlement pays **stored** `bet["odds"]`, never current odds.

## Deferred

- Over/under + spread bets (payload already has `total`/`pointSpread`)
- Odds-movement display (open vs close is already in the payload)
- Knockout markets
