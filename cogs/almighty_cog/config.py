"""Configuration constants for the Almighty cog (working title).

A persistent button lives in the "trigger" channel; pressing it opens a
form whose contents are posted to the "feed" channel. Both IDs are
overridable via env vars so they can change per deployment without code
edits.
"""

from typing import Final

from config import get_int_env

# Channel hosting the persistent trigger button.
TRIGGER_CHANNEL_ID: Final[int] = get_int_env("ALMIGHTY_TRIGGER_CHANNEL_ID", 1515639236164980778)

# Channel where submitted forms are posted.
FEED_CHANNEL_ID: Final[int] = get_int_env("ALMIGHTY_FEED_CHANNEL_ID", 1515641245471473704)

# Category options offered by the radio-group form. (label, description).
# Between 2 and 10 entries per the RadioGroup component limit.
CATEGORIES: Final[list[tuple[str, str]]] = [
    ("Question", "Ask something"),
    ("Idea", "Suggest an improvement"),
    ("Bug", "Report something broken"),
    ("Other", "Anything else"),
]
