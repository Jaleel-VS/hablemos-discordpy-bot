# Plan: `$wcbet` profile stats + parlay (accumulator) bets

Status: planned, not implemented. Two independent features specced together
because the profile card naturally surfaces parlay results. Build order:
stats first (cheap, no schema risk), parlays second (new table + flow).

Both build on the shipped wcbet feature (`plans/wcbet.md`), reusing
`wc_bets`, `wc_bet_wallets`, `wc_balance_log`, and the ESPN odds/results
pipeline already in place.

---

## Feature 2 — Profile / stats card (`$wcbetme`)

### Goal
A personal stats card a user can pull up (and optionally share) showing their
betting history at a glance. Pure read over existing data — no schema change.

### Entry points
| Trigger | Behaviour |
|---|---|
| `$wcbetme` prefix cmd | Posts the caller's stats card (public embed). |
| `$wcbetme @user` | Posts another user's card (read-only, no PII). |
| "📊 My stats" button in the panel | Same card, ephemeral. |

### Data — all derivable, no new tables
Single aggregate query over `wc_bets` for the user:

```sql
SELECT
    COUNT(*)                                              AS total_bets,
    COUNT(*) FILTER (WHERE status = 'won')                AS wins,
    COUNT(*) FILTER (WHERE status = 'lost')               AS losses,
    COUNT(*) FILTER (WHERE status = 'pending')            AS pending,
    COALESCE(SUM(stake), 0)                               AS total_staked,
    COALESCE(SUM(payout) FILTER (WHERE status='won'), 0)  AS total_won,
    COALESCE(MAX(payout), 0)                              AS biggest_win,
    COALESCE(MAX(odds) FILTER (WHERE status='won'), 0)    AS longest_odds_won
FROM wc_bets
WHERE user_id = $1;
```

Derived fields (computed in Python, not SQL):
- **Win rate** = `wins / (wins + losses)` (settled bets only; ignore pending).
- **Net profit** = `total_won - total_staked_on_settled`. Needs a second
  scalar: `SUM(stake) FILTER (WHERE status IN ('won','lost'))`.
- **Current balance** from `wc_bet_wallets` (already have `get_wc_wallet`).
- **Rank** = position in `get_wc_top_balances` (or a dedicated rank query:
  `SELECT COUNT(*)+1 FROM wc_bet_wallets WHERE balance > $user_balance AND guild_id=$g`).

### DB method (one new method in `WCBetsMixin`)
```python
async def get_wc_user_profile(self, user_id: int, guild_id: int) -> dict:
    """Aggregate betting profile: counts, win rate inputs, net profit, rank."""
```
Returns a flat dict the cog formats. Two queries (aggregate + rank), no writes.

### Card layout (embed)
```
📊  dudenamedzombie's betting profile
─────────────────────────────────────
💰 Balance        33,350   ( #2 of 14 )
📈 Net profit     +18,350
🎯 Record         7W · 4L  (64% win rate)
🎟️ Pending        2 bets · 23,850 staked
🏆 Biggest win    28,350
🐴 Longest odds   2.70x  (won)
```
-# Footer: total wagered lifetime, member since.

### Streak (optional, fold in here)
Compute current streak from settled bets ordered by `settled_at`:
```sql
SELECT status FROM wc_bets
WHERE user_id = $1 AND status IN ('won','lost')
ORDER BY settled_at DESC LIMIT 20;
```
Walk the list until status flips → "🔥 3-win streak" / "🥶 2-loss streak".
Cheap, no schema. Shown as a line on the card.

### Effort
~1 DB method + 1 prefix command + 1 panel button + embed builder.
No migration. ~120 lines. Low risk.

---

## Feature 4 — Parlay / accumulator bets

### What it is
One stake riding on **2–5 matches at once**. Every leg must win or the whole
parlay loses. Combined odds = product of each leg's decimal odds, so the
payouts get spicy fast (3 legs at ~2.0 each ≈ 8x).

This is the single biggest engagement driver in real betting: big multipliers,
shared tension, great "share to chat" material.

### The Discord constraint that shapes the design
The existing single-bet panel is a tight match → outcome → stake stepper that
rebuilds in place. A parlay needs a **multi-leg cart**: pick match+outcome,
add to slip, repeat, then one stake for the whole thing. That doesn't fit the
linear stepper, so parlays get their **own ephemeral builder view**
(`ParlayPanelView`) opened from a "🎰 Build a parlay" button on the main panel.

Discord limits we design within:
- **5 action rows max per message** (Components V2). Budget:
  1 match select, 1 outcome row, 1 "add leg" / stake / place row, plus text.
  → Keep the builder to **one leg-in-progress at a time**, with the running
  slip rendered as text. Legs already added are text lines, not components.
- **25 options per select** — fine, group stage has ≤16 bettable at once.
- **Ephemeral edits** — same `edit_message(view=self)` rebuild pattern as
  `BetPanelView`, so state lives on the view instance.

### Rules (kept simple for v1)
- 2–5 legs. Min 2 (a 1-leg parlay is just a single bet).
- **One leg per match** — can't parlay Canada-win AND Canada-draw.
- All legs must be on **bettable** (not-yet-kicked-off) matches at placement.
- Single stake for the whole parlay (deducted once).
- Odds **snapshotted per leg** at placement (same as single bets).
- Combined odds = `floor(stake * product(leg_odds) * 100) / 100` via integer
  math (extend `betting.payout` to take a list, or fold the product first).
- Settlement: a parlay settles only when **all its legs' matches** have
  results. Lost the moment any single leg loses.

### Schema — two new tables
```sql
CREATE TABLE wc_parlays (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES wc_bet_wallets(user_id),
    guild_id    BIGINT NOT NULL,
    stake       INTEGER NOT NULL CHECK (stake > 0),
    combined_odds NUMERIC(8,2) NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','won','lost','void')),
    payout      INTEGER,
    placed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at  TIMESTAMPTZ
);

CREATE TABLE wc_parlay_legs (
    parlay_id   BIGINT NOT NULL REFERENCES wc_parlays(id) ON DELETE CASCADE,
    match_id    INTEGER NOT NULL,
    outcome     TEXT NOT NULL CHECK (outcome IN ('home','draw','away')),
    odds        NUMERIC(5,2) NOT NULL,
    -- per-leg result, filled in as matches settle
    result      TEXT CHECK (result IN ('won','lost')),
    PRIMARY KEY (parlay_id, match_id)
);
CREATE INDEX idx_wc_parlay_legs_match ON wc_parlay_legs(match_id);
```
Kept separate from `wc_bets` so single-bet settlement logic stays untouched.

### Settlement integration (the tricky part)
`settle_wc_match(match_id, ...)` currently settles single bets on that match.
Parlays span multiple matches, so settling one match only resolves *one leg*.

Approach — settle legs incrementally, evaluate parlay when complete:
1. When a match settles, **also** update matching parlay legs:
   ```sql
   UPDATE wc_parlay_legs SET result =
       CASE WHEN outcome = $settled_outcome THEN 'won' ELSE 'lost' END
   WHERE match_id = $1 AND result IS NULL;
   ```
2. For each affected parlay:
   - If **any** leg is now `'lost'` → parlay `status='lost'`, payout 0,
     settle immediately (no need to wait for other legs).
   - If **all** legs `'won'` → parlay `status='won'`, credit
     `floor(stake * combined_odds)`, log `parlay_won` to `wc_balance_log`.
   - Otherwise still `pending`.
3. Do this inside the same `settle_wc_match` transaction so a parlay can never
   half-settle. Add a `_settle_parlay_legs(conn, match_id, outcome)` helper.

Edge: a **voided match** (`void_wc_match`) in a parlay → treat that leg as
removed and recompute combined odds (or simplest v1: **void the whole parlay**
and refund the stake, mirroring how single bets refund). Recommend whole-parlay
void for v1 — simpler, fair, rare.

### Builder view UX (`ParlayPanelView`)
```
## 🎰 Build a parlay        💰 33,350 coins
Legs (2/5):
  • 🇲🇽 Mexico to win @ 1.43
  • 🇺🇸 USA to win  @ 2.15
Combined odds: 3.07x

[ Choose a match…            ▼ ]   ← only matches not already in slip
[ 🏠 Home ]  [ 🤝 Draw ]  [ ✈️ Away ]   ← arms the in-progress leg
[ ➕ Add leg ] [ Stake… ▼ ] [ 💸 Place 5,000 → win 15,350 ]
[ 🗑️ Clear ] [ Cancel ]
```
- Match select excludes matches already in the slip.
- Outcome buttons arm the in-progress leg; "Add leg" commits it to the slip
  (text), clears the in-progress selection for the next.
- Stake select / Place only enabled at ≥2 legs.
- Place re-validates every leg is still bettable + re-fetches odds (drift
  guard, same as single bets), then writes parlay + legs + balance in one txn.

### DB methods
```python
async def place_wc_parlay(self, user_id, guild_id, stake, legs) -> int
    # legs: list[{match_id, outcome, odds}]; one txn: lock wallet, deduct,
    # insert parlay + legs, log balance event. Returns new balance.

async def _settle_parlay_legs(self, conn, match_id, outcome) -> list[dict]
    # called inside settle_wc_match; resolves legs, settles completed parlays,
    # credits winners. Returns settled-parlay summaries for announcing.

async def get_wc_user_parlays(self, user_id, status=None) -> list[dict]
    # for the profile card + share button (legs joined in).
```

### Settlement announcement
Parlays that resolve during a match settlement get their own notification
lines (reuse `format_player_results` style):
> 🎰 **Parlay landed!** @user 5,000 → **15,350** (3 legs @ 3.07x)
> 💥 **Parlay busted** @user (USA leg lost)

### Share integration
The existing "📣 Share bets" button should also list active parlays —
they're the most brag-worthy bets. Extend `_on_share_bets` to append parlay
lines after singles.

### Effort
Medium. New table migration, `ParlayPanelView` (~250 lines, mirrors
`BetPanelView` patterns), `place_wc_parlay` + leg-settlement woven into
`settle_wc_match`, 1 builder button, profile/share integration. The
settlement weaving is the highest-risk part — needs tests for: any-leg-loss,
all-legs-win, partial-pending, voided-leg.

### Suggested build order
1. Schema migration (both tables) + `place_wc_parlay` + unit tests for combined
   odds math.
2. `_settle_parlay_legs` woven into `settle_wc_match` + settlement tests
   (this is where correctness matters most — money).
3. `ParlayPanelView` builder + entry button.
4. Profile card parlay section + share-button integration + announcements.

---

## Docs to update when implemented
- `docs/cogs/wcbet.md` — new commands, parlay rules, settlement behaviour.
- `docs/commands.md` — `$wcbetme` blurb.
- `docs/db.md` — `wc_parlays`, `wc_parlay_legs` tables.
- `docs/admin.md` — note parlay handling in `$wcbetadmin result`/`void`.
