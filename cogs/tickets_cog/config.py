"""Configuration for the Tickets cog."""
from typing import Final

from config import get_int_env

STAFF_FORUM_ID: Final[int] = get_int_env("TICKETS_STAFF_FORUM_ID", 1226389895564492800)
ADMIN_FORUM_ID: Final[int] = get_int_env("TICKETS_ADMIN_FORUM_ID", 1226387256915263528)

# Tag names treated as "open" (case-insensitive match)
OPEN_TAGS: Final[list[str]] = ['Open']
