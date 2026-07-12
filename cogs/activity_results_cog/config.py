"""Configuration for the Activity results-poster cog."""
from config import get_int_env

# Channel where finished daily-game results (e.g. Wordle) are posted. Set to 0
# to disable posting entirely (the poller becomes a no-op). No baked-in default
# channel — this must be set per deployment.
ACTIVITY_RESULTS_CHANNEL_ID: int = get_int_env("ACTIVITY_RESULTS_CHANNEL_ID", 0)

# How often (seconds) the bot polls for unposted results.
ACTIVITY_RESULTS_POLL_SECONDS: int = get_int_env("ACTIVITY_RESULTS_POLL_SECONDS", 60)

# Max results posted per poll tick (avoids a burst flooding the channel after
# a backlog builds up).
ACTIVITY_RESULTS_BATCH: int = get_int_env("ACTIVITY_RESULTS_BATCH", 10)
