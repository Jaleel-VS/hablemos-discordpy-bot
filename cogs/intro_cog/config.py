"""Configuration for the Introduction Tracker cog."""
from config import load_settings

settings = load_settings()

# Cooldown window (days) before a user can post another introduction
INTRO_COOLDOWN_DAYS = 90

# Default configurable channel IDs (used if not set in DB)
DEFAULT_WARN_CHANNEL_ID = settings.intro_warn_channel_id
DEFAULT_ALERT_CHANNEL_ID = settings.intro_alert_channel_id

# DB setting keys
SETTING_WARN_CHANNEL = 'intro_warn_channel'
SETTING_ALERT_CHANNEL = 'intro_alert_channel'

# Exempt roles that can post multiple times
EXEMPT_ROLE_IDS = (
    643097537850376199,   # Rai
    243854949522472971,   # Admin
    1014256322436415580,  # Retired Mod
    258819531193974784,   # Server Staff
    591745589054668817,   # Trail Staff Helper
    1082402633979011082,  # Retired Staff
)
