"""World Cup betting cog configuration.

Reuses the World Cup log channel from `cogs.worldcup_cog.config` so all
World Cup activity routes to the same place. The odds constant is a
display/snapshot value only — payout math is pure integer arithmetic in
`cogs.wcbet_cog.betting.payout`.
"""
from cogs.worldcup_cog.config import WORLD_CUP_LOG_CHANNEL_ID
from config import get_int_env

# Coins granted once when a user opts in.
WCBET_STARTING_BALANCE: int = 10_000

# Coins granted on the first `$wcbet` interaction of each UTC day.
WCBET_DAILY_ALLOWANCE: int = 500

# Flat odds, stored per-bet for future variable odds. Display only:
# the actual payout is computed as `stake * 3 // 2` (see betting.payout).
WCBET_ODDS: float = 1.5

# Results poller mode. 0 (default) = propose: post the finished score to
# the log channel with the `$wcbetadmin result` command to run. 1 = auto:
# settle bets immediately when ESPN reports the match completed.
WCBET_AUTO_SETTLE: bool = get_int_env("WCBET_AUTO_SETTLE", 0) == 1

# Minutes between results polls (only fires while a match is in its
# post-kickoff window, so idle traffic is zero).
WCBET_RESULTS_POLL_MINUTES: int = get_int_env("WCBET_RESULTS_POLL_MINUTES", 5)

# Re-exported so the cog only imports from one place.
WCBET_LOG_CHANNEL_ID: int = WORLD_CUP_LOG_CHANNEL_ID

__all__ = [
    "WCBET_AUTO_SETTLE",
    "WCBET_DAILY_ALLOWANCE",
    "WCBET_LOG_CHANNEL_ID",
    "WCBET_ODDS",
    "WCBET_RESULTS_POLL_MINUTES",
    "WCBET_STARTING_BALANCE",
]
