# Hablemos

A Spanish-English language learning Discord bot for the [Spanish-English Learning Server](https://discord.gg/spanish-english).

Built with discord.py 2.x, PostgreSQL (asyncpg), and Google Gemini. Deployed on Railway via Docker.

## Features

- **AI Conversations** — Practice with realistic dialogues powered by Google Gemini
- **Language League** — Competitive leaderboard system with biweekly rounds and consistency rewards
- **Vocabulary Tools** — Personal vocab notes with search, export, and synonyms/antonyms lookup
- **Interactive Games** — Conjugation practice, Hangman, conversation starters
- **Moderation Tools** — AI-powered conversation summaries, introduction tracking
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

### Conjugation Practice

| Command | Description |
|---------|-------------|
| `$conj [category] [questions]` | Start a conjugation practice session |
| `$conj_categories` | List available verb categories |
| `$conj_stop` | Stop your current session |

Categories: `high-frequency`, `regular-ar`, `regular-er-ir`, `irregulars`. Supports present, preterite, and future tenses with lenient answer checking (accent-insensitive, pronoun-optional).

### Vocabulary Notes

All responses are ephemeral (private to the user).

| Command | Description |
|---------|-------------|
| `/vocab add` | Add a vocabulary note (opens form) |
| `/vocab list [limit]` | View your notes (max 50) |
| `/vocab search <query>` | Search by word or translation |
| `/vocab delete <note_id>` | Delete a note |
| `/vocab export` | Export all notes to CSV |

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

### Synonyms & Antonyms

| Command | Description |
|---------|-------------|
| `$sinonimos <word>` | Find Spanish synonyms |
| `$antonimos <word>` | Find Spanish antonyms |

Sourced from WordReference with a 24-hour cache. 15-second cooldown.

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
| `$summarize <message_link> [count]` | AI-summarize a conversation (Moderator) |
| `$introtracker [on\|off\|status]` | Toggle introduction tracking (Moderator) |
| `$introstatus` | Introduction tracker statistics (Moderator) |
| `$parrot <guild_id> <channel_id> <message>` | Relay a message to another channel (Owner) |

Summaries analyze 1–500 messages with a 1-hour cache. Introduction tracking prevents duplicate posts within a 90-day window.

---

## Setup

### Environment Variables

```bash
BOT_TOKEN=           # Discord bot token (required)
DATABASE_URL=        # PostgreSQL connection string (required)
GEMINI_API_KEY=      # Google Gemini API key (required for AI features)
PREFIX=$             # Command prefix (default: $)
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

## License

MIT
