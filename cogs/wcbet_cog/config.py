"""World Cup betting cog configuration.

Reuses the World Cup log channel from `cogs.worldcup_cog.config` so all
World Cup activity routes to the same place. Live odds come from
DraftKings via ESPN (see `espn.py`); `WCBET_ODDS` is the flat fallback
when a match has no line.
"""
from decimal import Decimal

from cogs.worldcup_cog.config import WORLD_CUP_LOG_CHANNEL_ID
from config import get_int_env

# Coins granted once when a user opts in.
WCBET_STARTING_BALANCE: int = 10_000

# Coins granted on the first `$wcbet` interaction of each UTC day.
WCBET_DAILY_ALLOWANCE: int = 2_500

# Max parlays a user may have pending (unsettled) at any one time. Caps
# parlay-farming: a user must let existing parlays settle before stacking
# more. Enforced authoritatively inside the place_wc_parlay transaction.
WCBET_MAX_PENDING_PARLAYS: int = get_int_env("WCBET_MAX_PENDING_PARLAYS", 2)

# Fallback odds when DraftKings has not priced a match (or the fetch
# fails); also the snapshot stored on such bets. Payouts are computed
# as floor(stake * odds) in integer math (see betting.payout).
WCBET_ODDS: Decimal = Decimal("1.5")

# Results poller mode. 0 (default) = propose: post the finished score to
# the log channel with the `$wcbetadmin result` command to run. 1 = auto:
# settle bets immediately when ESPN reports the match completed.
WCBET_AUTO_SETTLE: bool = get_int_env("WCBET_AUTO_SETTLE", 0) == 1

# Minutes between results polls (only fires while a match is in its
# post-kickoff window, so idle traffic is zero).
WCBET_RESULTS_POLL_MINUTES: int = get_int_env("WCBET_RESULTS_POLL_MINUTES", 5)

# Max bets rendered in the panel's "My bets" view. Discord's Components V2
# TextDisplay is capped at 4,000 chars; a heavy bettor's full history
# across the 72-match group stage (plus settled/replaced rows) would blow
# past that and the whole panel would fail to render. Cap the view and
# point overflow at `$wcbethistory` for the full wallet log.
WCBET_MY_BETS_LIMIT: int = 20

# Re-exported so the cog only imports from one place.
WCBET_LOG_CHANNEL_ID: int = WORLD_CUP_LOG_CHANNEL_ID

# Channel where per-player win/loss mentions are posted after settlement.
WCBET_NOTIFICATION_CHANNEL_ID: int = get_int_env("WCBET_NOTIFICATION_CHANNEL_ID", 247135634265735168)

__all__ = [
    "WCBET_AUTO_SETTLE",
    "WCBET_DAILY_ALLOWANCE",
    "WCBET_LOG_CHANNEL_ID",
    "WCBET_MAX_PENDING_PARLAYS",
    "WCBET_MY_BETS_LIMIT",
    "WCBET_NOTIFICATION_CHANNEL_ID",
    "WCBET_ODDS",
    "WCBET_RESULTS_POLL_MINUTES",
    "WCBET_STARTING_BALANCE",
]
