"""Configuration for the Introduction Tracker cog."""
from config import load_settings

settings = load_settings()

# Channel IDs
INTRO_CHANNEL_ID = settings.intro_channel_id
GENERAL_CHANNEL_ID = settings.general_channel_id

# Default configurable channel IDs (used if not set in DB)
DEFAULT_WARN_CHANNEL_ID = settings.intro_warn_channel_id
DEFAULT_ALERT_CHANNEL_ID = settings.intro_alert_channel_id

# DB setting keys
SETTING_WARN_CHANNEL = 'intro_warn_channel'
SETTING_ALERT_CHANNEL = 'intro_alert_channel'

# Exemptions - Users and roles that can post multiple times
EXEMPT_ROLE_IDS = (
    643097537850376199,   # Rai
    243854949522472971,   # Admin
    1014256322436415580,  # Retired Mod
    258819531193974784,   # Server Staff
    591745589054668817,   # Trail Staff Helper
    1082402633979011082,  # Retired Staff
)

EXEMPT_USER_IDS = (
    202995638860906496,  # Ryan
)
