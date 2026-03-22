"""Configuration for the Tickets cog."""
import os

# Forum channel IDs
STAFF_FORUM_ID = int(os.getenv('STAFF_FORUM_ID', '0'))
ADMIN_FORUM_ID = int(os.getenv('ADMIN_FORUM_ID', '0'))

# Tag names treated as "open" (case-insensitive match)
OPEN_TAGS = os.getenv('TICKETS_OPEN_TAGS', 'Open,Ban Appeal').split(',')
