# Hablemos

A Spanish-English language learning Discord bot for the [Spanish-English Learning Server](https://discord.gg/spanish-english).

Built with discord.py 2.x, PostgreSQL (asyncpg), and Google Gemini. Deployed on Railway via Docker.

## Features

- **AI Conversations** — Practice with realistic dialogues powered by Google Gemini
- **AI Ask** — Owner-only freeform Gemini Q&A with paginated, public/private responses
- **Language League** — Competitive leaderboard system with biweekly rounds and consistency rewards
- **Vocabulary Tools** — Personal vocab notes with search, export, and SRS practice
- **Interactive Games** — Conjugation practice, Hangman, conversation starters
- **Moderation Tools** — AI-powered conversation summaries, introduction tracking, ticket overview
- **Bot Administration** — Cog toggle system, command metrics, data retention, interaction analysis
- **Quote Generator** — Create shareable quote images from messages
- **Spotify Integration** — See what users are listening to

---

## Commands

### General

| Command | Description |
|---------|-------------|
| `/help [category]` | Interactive help with categories |
| `$help [command]` | Detailed usage for a specific command |
| `$info` | Bot information and links |
| `$ping` | Check bot latency |
| `$lst` | List conversation topic categories |

### AI Conversations

Generate realistic conversations for language practice.

| Command | Description |
|---------|-------------|
| `$convo [language] [level] [category]` | Get a random AI-generated conversation |

Languages: `spanish`, `english` — Levels: `beginner`, `intermediate`, `advanced` — Categories: `restaurant`, `travel`, `shopping`, `workplace`, `social`

Daily limit of 2 per user (unlimited for moderators). Conversations regenerate automatically when exhausted.

### AI Ask

| Command | Description |
|---------|-------------|
| `$ask <question>` | Ask Gemini anything (Owner) |

Responses are generated with a 30-second timeout. After generation, choose to send publicly, send privately (ephemeral), or discard. Long responses are automatically paginated.

### Conjugation Practice

| Command | Description |
|---------|-------------|
| `$conj [category] [questions]` | Start a conjugation practice session |
| `$conj_categories` | List available verb categories |
| `$conj_stop` | Stop your current session |

Categories: `high-frequency`, `regular-ar`, `regular-er-ir`, `irregulars`. Supports present, preterite, and future tenses with lenient answer checking (accent-insensitive, pronoun-optional). 59 verbs, 1,062 combinations.

### Vocabulary Notes

All responses are ephemeral (private to the user).

| Command | Description |
|---------|-------------|
| `/vocab add` | Add a vocabulary note (opens form) |
| `/vocab list [limit]` | View your notes (max 50) |
| `/vocab search <query>` | Search by word or translation |
| `/vocab delete <note_id>` | Delete a note |
| `/vocab export` | Export all notes to CSV |

### Vocabulary Practice (SRS)

Clozemaster-style spaced repetition using your saved vocab notes.

| Command | Description |
|---------|-------------|
| `$practice` | Start a practice session with due cards |

### Language League

Opt-in competitive system that tracks language practice activity across biweekly rounds.

| Command | Description |
|---------|-------------|
| `/league join` | Join the competition |
| `/league leave` | Opt out (preserves history) |
| `/league view [board] [limit]` | View rankings (spanish, english, or combined) |
| `/league stats [@user]` | View stats for yourself or another user |

**Scoring:** `Total = Message Points + (Active Days x 5)`. Anti-spam measures include language detection, 2-minute per-channel cooldowns, 10-character minimum, and a 50-message daily cap.

**Requirements:** Must have exactly one Learning role (Spanish or English). Cannot be native in the language you're learning.

Admin commands (`$league ban/unban/exclude/include/endround/preview`) are owner-only.

### Hangman

| Command | Description |
|---------|-------------|
| `$hangman [category]` | Start a game |
| `$hangman_status` | Check active games |

Categories: `animales` (199 words), `profesiones` (141), `ciudades` (49). One game per channel, 45-second inactivity timeout.

### Conversation Starters

| Command | Description |
|---------|-------------|
| `$topic [category]` | Get a random bilingual conversation starter |

Categories: `general` (1), `phil` (2), `would` (3), `other` (4). Channel-aware — Spanish channels show Spanish first.

### Spotify

| Command | Description |
|---------|-------------|
| `$nowplaying [@user]` | Show current Spotify activity |

Aliases: `$spoti`, `$np`. Also available as a slash command.

### Quote Generator

| Command | Description |
|---------|-------------|
| `$quote [message_link\|text]` | Generate a quote image (style 1) |
| `$quote2 [message_link\|text]` | Generate a quote image (style 2) |

Reply to a message, provide a link, or type custom text. 150-character limit, 10-second cooldown.

### Moderation

| Command | Description |
|---------|-------------|
| `$summarize <start_link> <end_link>` | AI-summarize a message range (Moderator) |
| `$tickets` | Show open mod tickets across forum channels (Moderator) |
| `$introtracker [on\|off\|status]` | Toggle introduction tracking (Moderator) |
| `$introstatus` | Introduction tracker statistics (Moderator) |
| `$parrot <guild_id> <channel_id> <message>` | Relay a message to another channel (Owner) |

Summaries analyze the range between two message links with a 1-hour cache. Ticket overview shows open threads from staff and admin modbot forums with response status.

### Administration

| Command | Description |
|---------|-------------|
| `$cog list` | List all cogs and their status (Owner) |
| `$cog enable <name>` | Enable a disabled cog (Owner) |
| `$cog disable <name>` | Disable a cog at next restart (Owner) |
| `$cog reload <name>` | Hot-reload a cog (Owner) |
| `$metrics [days]` | Command usage stats (Owner) |
| `$metrics hours [days]` | Usage by hour of day (Owner) |
| `$metrics user @member [days]` | Per-user command stats (Owner) |
| `$metrics retention` | Table sizes and row counts (Owner) |
| `$metrics cleanup` | Manually trigger data retention cleanup (Owner) |
| `$interactions [#channel] [days]` | Analyze reply/mention pairs in a channel (Owner) |

Data retention runs daily: rolls up command metrics older than 30 days, purges stale league activity.

---

## Setup

### Environment Variables

```bash
BOT_TOKEN=           # Discord bot token (required)
DATABASE_URL=        # PostgreSQL connection string (required)
GEMINI_API_KEY=      # Google Gemini API key (required for AI features)
PREFIX=$             # Command prefix (default: $)
WEBSITE_API_URL=     # Website API base URL (optional)
CONVO_SPA_CHANNELS=  # Comma-delimited Spanish-first channel IDs (optional)
INTRO_CHANNEL_ID=    # Intro channel ID (optional)
GENERAL_CHANNEL_ID=  # General channel ID (optional)
INTRO_WARN_CHANNEL_ID=  # Intro warning channel ID (optional)
INTRO_ALERT_CHANNEL_ID= # Intro alert channel ID (optional)
```

### Run Locally

```bash
pip install -r requirements.txt
python hablemos.py
```

### Docker

```bash
docker build -t hablemos-bot .
docker run -d --env-file .env hablemos-bot
```

---

## Architecture

```
hablemos.py              Bot entrypoint
base_cog.py              Base class for all cogs
logger.py                Logging configuration
db/
  __init__.py            Database class (composes domain mixins)
  schema.py              Table definitions and migrations
  <domain>.py            Query methods per domain
cogs/<feature>_cog/
  main.py                Cog class + setup() (auto-loaded)
  admin.py               Admin commands (optional)
  config.py              Cog-specific constants (optional)
cogs/utils/
  embeds.py              Shared embed helpers
  rate_limiter.py        Shared API rate limiter
```

Cogs are auto-discovered at startup. Database access is via `self.bot.db` (asyncpg connection pool). See [AGENTS.md](AGENTS.md) for full development guidelines.

---

## TODO

- [ ] AI ticket triage — priority suggestions and action steps for open mod tickets
- [ ] Daily word of the day — scheduled post with conjugation/usage examples
- [ ] Practice streak tracking — consecutive day counter for active learners
- [ ] Vocab quiz — self-test on saved vocabulary notes
- [ ] Interactive AI conversations — user plays one speaker, Gemini plays the other
- [ ] Leaderboard history — past round winners and rank progression
- [ ] Practice reminders — opt-in daily DM when SRS cards are due
- [ ] Listening comprehension — TTS audio of generated dialogues
- [ ] Error pattern analysis — track weak spots in conjugation practice

## To-fix

- [ ] Centralize env var validation to avoid per-cog duplication
- [ ] Align cog error handling so failures log once and user feedback is consistent
- [ ] Harden on_ready channel/guild fetch handling with safe fallbacks
- [ ] Prefer asyncio.get_running_loop() over get_event_loop() in async code
- [ ] Guard against double-including boundary messages in summaries

---

## License

MIT
