"""Configuration for the Introduction Tracker cog."""
from config import get_int_env

INTRO_COOLDOWN_DAYS = 90

INTRO_CHANNEL_ID = get_int_env("INTRO_CHANNEL_ID", 399713966781235200)
GENERAL_CHANNEL_ID = get_int_env("GENERAL_CHANNEL_ID", 296491080881537024)
DEFAULT_WARN_CHANNEL_ID = get_int_env("INTRO_WARN_CHANNEL_ID", 247135634265735168)
DEFAULT_ALERT_CHANNEL_ID = get_int_env("INTRO_ALERT_CHANNEL_ID", 297877202538594304)

SETTING_WARN_CHANNEL = 'intro_warn_channel'
SETTING_ALERT_CHANNEL = 'intro_alert_channel'

EXEMPT_ROLE_IDS = (
    643097537850376199,   # Rai
    243854949522472971,   # Admin
    1014256322436415580,  # Retired Mod
    258819531193974784,   # Server Staff
    591745589054668817,   # Trail Staff Helper
    1082402633979011082,  # Retired Staff
)

# Minimum role allowed to use $resetintro (this role and any higher role);
# falls back to Manage Messages if the role is missing/misconfigured.
RESETINTRO_ROLE_ID = 591745589054668817  # Trail Staff Helper
