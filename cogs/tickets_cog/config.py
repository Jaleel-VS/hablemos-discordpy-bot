"""Configuration for the Tickets cog."""
from typing import Final

from config import get_int_env

STAFF_FORUM_ID: Final[int] = get_int_env("TICKETS_STAFF_FORUM_ID", 1226389895564492800)
ADMIN_FORUM_ID: Final[int] = get_int_env("TICKETS_ADMIN_FORUM_ID", 1226387256915263528)

# Channel where new-ticket pings are posted. 0 disables the ping listener.
NOTIFY_CHANNEL_ID: Final[int] = get_int_env("TICKETS_NOTIFY_CHANNEL_ID", 297877202538594304)

# Minimum role required to use $ticketsub. 0 = fall back to manage_messages.
TICKETSUB_MIN_ROLE_ID: Final[int] = get_int_env("TICKETSUB_MIN_ROLE_ID", 0)

# Tag names treated as "open" (case-insensitive match)
OPEN_TAGS: Final[list[str]] = ['Open']

# Thread names to exclude from the ticket list (case-insensitive)
FILTERED_THREADS: Final[set[str]] = {"meta discussion"}
