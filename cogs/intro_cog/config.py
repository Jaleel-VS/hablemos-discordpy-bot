"""Configuration for the Introduction Tracker cog."""
import os

# Channel IDs
INTRO_CHANNEL_ID = int(os.getenv('INTRO_CHANNEL_ID', '399713966781235200'))
GENERAL_CHANNEL_ID = int(os.getenv('GENERAL_CHANNEL_ID', '296491080881537024'))

# Default configurable channel IDs (used if not set in DB)
DEFAULT_WARN_CHANNEL_ID = int(os.getenv('INTRO_WARN_CHANNEL_ID', '247135634265735168'))
DEFAULT_ALERT_CHANNEL_ID = int(os.getenv('INTRO_ALERT_CHANNEL_ID', '297877202538594304'))

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
