"""World Cup predictions cog configuration.

Reuses the World Cup log channel from `cogs.worldcup_cog.config` so all
World Cup activity routes to the same place. Settings that vary at
runtime (deadline, actual champion) live in the `bot_settings` table.
"""
from cogs.worldcup_cog.config import WORLD_CUP_LOG_CHANNEL_ID
from config import get_int_env

# Optional fallback deadline as a Unix epoch (seconds). 0 means
# "no deadline configured" — predictions stay open until an admin sets
# one via `$wcpredict setdeadline`.
WC_PREDICT_DEFAULT_DEADLINE_TS: int = get_int_env("WC_PREDICT_DEFAULT_DEADLINE_TS", 0)

# bot_settings keys
SETTING_KEY_DEADLINE = "wc_predict.deadline_ts"
SETTING_KEY_WINNER = "wc_predict.winner_role_id"

# Re-exported so the cog only imports from one place.
WC_PREDICT_LOG_CHANNEL_ID = WORLD_CUP_LOG_CHANNEL_ID

__all__ = [
    "SETTING_KEY_DEADLINE",
    "SETTING_KEY_WINNER",
    "WC_PREDICT_DEFAULT_DEADLINE_TS",
    "WC_PREDICT_LOG_CHANNEL_ID",
]
