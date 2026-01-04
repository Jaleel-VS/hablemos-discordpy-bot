# Language League Cog

A modular Discord bot cog for managing language learning competitions.

## Architecture

This cog has been refactored following clean architecture principles:

```
cogs/league_cog/
├── main.py              # User-facing features (slash commands, message tracking)
├── admin.py             # Admin-only commands (owner permissions required)
├── utils.py             # Shared utilities (language detection, regex patterns)
├── config.py            # Configuration constants
└── league_helper/       # Helper modules (image generation, etc.)
    └── leaderboard_image_pillow.py
```

## Module Responsibilities

### main.py (LeagueCog)
**Purpose:** User-facing league functionality

**Features:**
- `/league join` - Join the language league
- `/league leave` - Leave the language league
- `/league view` - View leaderboard rankings
- `/league stats` - View personal or user stats
- Message tracking and scoring
- Round management (automatic round end/start)
- Winner announcements

**Key Components:**
- Role validation system
- Message cooldown tracking
- Language detection integration
- Round scheduling (checks every 1 minute)

### admin.py (LeagueAdminCog)
**Purpose:** Admin tools and debugging (owner-only)

**Commands:**
- `$league ban <user>` - Ban user from league
- `$league unban <user>` - Unban user
- `$league exclude <#channel>` - Exclude channel from tracking
- `$league include <#channel>` - Re-include channel
- `$league excluded` - List excluded channels
- `$league admin_stats` - Show league statistics
- `$league validatemessage <link>` - Debug message language detection
- `$league audit <user>` - Show last 3 counted messages for verification

**Key Components:**
- User management (banning/unbanning)
- Channel exclusion system
- Audit tools for debugging
- Statistics dashboard

### utils.py
**Purpose:** Shared utilities used by both cogs

**Functions:**
- `detect_message_language(content)` - Detects Spanish/English from message text
  - Removes emojis (custom Discord + Unicode)
  - Validates minimum length
  - Returns 'es', 'en', or None

**Constants:**
- `CUSTOM_EMOJI_PATTERN` - Regex for Discord emojis
- `UNICODE_EMOJI_PATTERN` - Regex for Unicode emojis

## Design Principles Applied

1. **Separation of Concerns**
   - User features and admin features are completely separate
   - Shared code extracted to utils module
   - Each file has a single, clear responsibility

2. **DRY (Don't Repeat Yourself)**
   - Language detection logic in one place
   - Emoji patterns defined once
   - Both cogs can use shared utilities

3. **Single Responsibility Principle**
   - LeagueCog: Handles user interactions and league mechanics
   - LeagueAdminCog: Handles admin operations and debugging
   - utils.py: Provides shared helper functions

4. **Maintainability**
   - Admin features can evolve independently
   - User features can be updated without touching admin code
   - Utilities are tested once, used everywhere

## Loading

Both cogs are loaded from `main.py`'s setup function:

```python
async def setup(bot):
    await bot.add_cog(LeagueCog(bot))
    await bot.add_cog(LeagueAdminCog(bot))
```

This ensures both cogs are always loaded together when the league_cog module loads.

## Configuration

All configuration is centralized in `config.py`:

- `LEAGUE_GUILD_ID` - Server ID where league is active
- `WINNER_CHANNEL_ID` - Channel for winner announcements
- `ROLES` - Role IDs for validation
- `SCORING` - Points and multipliers
- `RATE_LIMITS` - Anti-spam settings
- `ROUNDS` - Round duration and check intervals
- `DISPLAY` - UI strings and emojis
- `LANGUAGE` - Language detection settings

## Future Enhancements

With this architecture, it's easy to:

- Add new admin commands without touching user code
- Add new user features without bloating admin tools
- Test components independently
- Extract more shared utilities as needed
- Add more specialized cogs (analytics, reports, etc.)
