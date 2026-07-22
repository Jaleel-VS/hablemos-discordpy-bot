"""Database mixin for automod watch settings."""
from db import DatabaseMixin

# bot_settings keys
KEY_LOG_CHANNEL = "automod_watch.log_channel_id"
KEY_ALERT_CHANNEL = "automod_watch.alert_channel_id"
KEY_THRESHOLD = "automod_watch.threshold"
KEY_WINDOW = "automod_watch.window_seconds"

DEFAULT_THRESHOLD = 2
DEFAULT_WINDOW = 300  # 5 minutes


class AutomodWatchMixin(DatabaseMixin):
    """Settings accessors for the automod-watch feature.

    All values live in the existing `bot_settings` table so no schema
    migration is needed.
    """

    async def get_automod_watch_config(self) -> dict:
        """Return all automod-watch settings as a single dict with defaults applied."""
        rows = await self._fetch(
            """
            SELECT setting_key, setting_value
            FROM bot_settings
            WHERE setting_key = ANY($1)
            """,
            [KEY_LOG_CHANNEL, KEY_ALERT_CHANNEL, KEY_THRESHOLD, KEY_WINDOW],
        )
        raw = {r["setting_key"]: r["setting_value"] for r in rows}
        return {
            "log_channel_id": raw.get(KEY_LOG_CHANNEL),
            "alert_channel_id": raw.get(KEY_ALERT_CHANNEL),
            "threshold": raw.get(KEY_THRESHOLD, DEFAULT_THRESHOLD),
            "window_seconds": raw.get(KEY_WINDOW, DEFAULT_WINDOW),
        }
