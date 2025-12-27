# Hablemos 🗣

A comprehensive Spanish-English language learning Discord bot for the [Spanish-English Learning Server](https://discord.gg/spanish-english).

## Overview

Hablemos is a feature-rich bot designed to help users learn Spanish and English through interactive games, AI-powered conversations, vocabulary tools, and community engagement features.

## Features

- 🤖 **AI-Generated Conversations** - Practice with realistic dialogues powered by Google Gemini
- 🏆 **Language League** - Compete with other learners, track progress, earn rewards for consistency
- 📚 **Vocabulary Tools** - Personal vocab notes with export, synonyms/antonyms lookup
- 🎮 **Interactive Games** - Conjugation practice, Hangman, conversation starters
- 🎵 **Spotify Integration** - See what users are listening to
- 📝 **Moderation Tools** - AI summaries, introduction tracking
- 🖼️ **Quote Generator** - Create shareable quote images

---

## Commands

- [General](#general)
- [Language Learning](#language-learning)
  - [AI Conversations](#ai-conversations)
  - [Conjugation Practice](#conjugation-practice)
  - [Vocabulary Notes](#vocabulary-notes)
  - [Language League](#language-league)
  - [Synonyms & Antonyms](#synonyms--antonyms)
- [Games](#games)
  - [Hangman](#hangman)
  - [Conversation Starters](#conversation-starters)
- [Social](#social)
  - [Spotify](#spotify)
  - [Quote Generator](#quote-generator)
- [Moderation](#moderation)

---

## General

Basic bot information and utilities.

| Command | Description |
|---------|-------------|
| `/help [category]` | Interactive help with categories (slash command) |
| `$help [command]` | Shows available commands and detailed usage information |
| `$info` | Information about the bot and links |
| `$invite` | Get an invite link for the bot |
| `$ping` | Check bot latency |
| `$lst` | Lists available conversation topic categories |

---

## Language Learning

### AI Conversations

Generate realistic conversations for language practice using Google Gemini AI.

| Command | Description |
|---------|-------------|
| `$convo [language] [level] [category]` | Get a random AI-generated conversation |

**Parameters:**
- **Language:** `spanish`, `english` (or aliases: `spa`, `es`, `eng`, `en`)
- **Level:** `beginner`, `intermediate`, `advanced` (or aliases: `beg`, `int`, `adv`, `a1`, `b1`, `c1`)
- **Category:** `restaurant`, `travel`, `shopping`, `workplace`, `social`

**Examples:**
```
$convo                                    # Random beginner conversation
$convo spanish                            # Random beginner Spanish conversation
$convo spanish intermediate               # Random intermediate Spanish conversation
$convo spanish intermediate restaurant    # Specific combination
```

**Features:**
- 5 categories × 3 levels × 2 languages = 30 conversation types
- Daily limit: 2 conversations per day (unlimited for moderators)
- Automatic regeneration when conversations are exhausted
- Natural, culturally-appropriate dialogues

**Admin Commands:**
- `$setup_convos` - Generate initial conversation database (Moderator only)
- `$convo_stats` - View conversation statistics (Owner only)

---

### Conjugation Practice

Interactive Spanish verb conjugation game.

| Command | Description |
|---------|-------------|
| `$conj [category] [questions]` | Start a conjugation practice session |
| `$conj_categories` | List available verb categories |
| `$conj_stop` | Stop your current practice session |

**Categories:**
- `high-frequency` - Most common Spanish verbs
- `regular-ar` - Regular -AR verbs
- `regular-er-ir` - Regular -ER and -IR verbs
- `irregulars` - Irregular verbs

**Features:**
- Practice present, preterite, and future tenses
- 1-30 questions per session
- Lenient answer checking (accent-insensitive, pronoun-optional)
- Real-time scoring and progress tracking
- One active game per user

**Example:**
```
$conj high-frequency 10    # Practice 10 high-frequency verbs
$conj irregulars           # Practice irregular verbs (default 5 questions)
```

---

### Vocabulary Notes

Personal vocabulary note management with privacy-focused ephemeral messages.

| Command | Description |
|---------|-------------|
| `/vocab add` | Add a new vocabulary note (opens form) |
| `/vocab list [limit]` | View your vocabulary notes (max 50) |
| `/vocab search <query>` | Search your notes by word or translation |
| `/vocab delete <note_id>` | Delete a specific note |
| `/vocab export` | Export all notes to CSV file |

**Features:**
- ✅ **Ephemeral messages** - Only you can see your notes
- ✅ **Modal form** - Easy multi-field input for adding notes
- ✅ **CSV Export** - Download all notes for backup or external use
- ✅ **Search** - Find notes quickly
- ✅ **Database-backed** - Your notes are saved permanently

**Add Note Fields:**
- Word/Phrase (required)
- Translation/Definition (optional, multi-line)
- Language (optional, e.g., "spanish", "english")

---

### Language League

Opt-in competitive leaderboard system that tracks and ranks language learning activity.

| Command | Description |
|---------|-------------|
| `/league join` | Join the Language League competition |
| `/league leave` | Opt out of the league (preserves historical data) |
| `/league view [spanish\|english\|combined] [limit]` | View league rankings |
| `/league stats [@user]` | View your stats or another user's stats |

**Admin Commands (Owner only):**
- `$league ban <@user>` - Ban user from league
- `$league unban <@user>` - Unban user from league
- `$league exclude <#channel>` - Exclude channel from tracking
- `$league include <#channel>` - Include previously excluded channel
- `$league excluded` - List all excluded channels

**How It Works:**

1. **Choose ONE Language** - Pick Spanish OR English to focus on
2. **Practice with Real Messages** - Only messages in your learning language count
3. **Quality Over Quantity** - Anti-spam measures reward genuine practice
4. **Earn Consistency Bonuses** - +5 points for each day you're active
5. **Compete in Biweekly Rounds** - Each round lasts 2 weeks, ending Sunday at midnight UTC
6. **Win Awards** - #1 winners get a star ⭐ next to their name in future rounds

**Scoring System:**
```
Total Score = Message Points + (Active Days × 5)

Example:
- 100 messages across 20 days = 100 + (20 × 5) = 200 points
```

**Requirements to Join:**
- ✅ Must have ONE Learning role (Learning Spanish OR Learning English)
- ❌ Cannot be native in the language you're learning
- ✅ Cannot have both Learning roles (choose one language to focus on)

**Anti-Spam Protection:**
- **Minimum message length:** 10 characters (to ensure language detection works)
- **Language detection:** Automatic detection ensures you're writing in your target language
- **2-minute cooldown:** Per channel (prevents rapid-fire spam)
- **Daily cap:** Maximum 50 counted messages per day
- **Excluded channels:** Admin-configured channels don't count (e.g., bot commands)

**Three Leaderboards:**
- **Spanish League** 🇪🇸 - Only users learning Spanish
- **English League** 🇬🇧 - Only users learning English
- **Combined League** 🌍 - All league participants

**Features:**
- ✅ **Biweekly rounds** - Fresh competition every 2 weeks with automatic transitions
- ✅ **Winner announcements** - Top 3 users announced at end of each round
- ✅ **Award system** - #1 winners get permanent star ⭐ recognition
- ✅ **Guild-specific** - Only available in authorized servers
- ✅ **Privacy-focused** - Ephemeral messages for opt-in/stats
- ✅ **Language detection** - Powered by `langdetect` library
- ✅ **Consistency rewards** - Encourages daily practice
- ✅ **Fair competition** - Multiple anti-gaming measures

**Stats Tracked:**
- Total message points
- Number of active days
- Total score (points + consistency bonus)
- Rankings on each applicable leaderboard

**Example Flow:**
```
1. /league join → Choose your learning language
2. Write messages in your target language (Spanish or English)
3. Bot automatically counts valid messages
4. /league stats → Check your progress
5. /league view spanish → See where you rank
```

---

### Synonyms & Antonyms

Spanish synonym and antonym lookup using WordReference.

| Command | Description |
|---------|-------------|
| `$sinonimos <word>` | Find Spanish synonyms |
| `$antonimos <word>` | Find Spanish antonyms |
| `$sinonimos_help` | Show usage help |

**Features:**
- Web scraping from WordReference.com
- Multiple synonym/antonym groups for different meanings
- 24-hour cache system
- Shows up to 15 results per group
- Cooldown: 15 seconds per user

**Example:**
```
$sinonimos feliz    # Find synonyms for "feliz"
$antonimos grande   # Find antonyms for "grande"
```

---

## Games

### Hangman

Classic word guessing game with Spanish vocabulary.

| Command | Description |
|---------|-------------|
| `$hangman [category]` | Start a Hangman game |
| `$hangman_status` | Check current game status |

**Categories:**
- `animales` (199 words) - Default
- `profesiones` (141 words)
- `ciudades` (49 Spanish-speaking cities)

**Features:**
- Interactive letter guessing
- 45-second inactivity timeout
- One game per channel
- Visual hangman display
- Game starter can quit anytime

---

### Conversation Starters

Random conversation topic suggestions in Spanish and English.

| Command | Description |
|---------|-------------|
| `$topic [category]` | Get a random conversation starter |

**Categories:**
- `general` (1) - General questions (default)
- `phil` (2) - Philosophical questions
- `would` (3) - "Would you rather" questions
- `other` (4) - Random questions

**Features:**
- Bilingual display (Spanish/English)
- Channel-aware (Spanish channels show Spanish first)
- [View all questions](https://docs.google.com/spreadsheets/d/10jsNQsSG9mbLZgDoYIdVrbogVSN7eAKbOfCASA5hN0A/)

---

## Social

### Spotify

See what users are listening to on Spotify.

| Command | Description |
|---------|-------------|
| `$nowplaying [@user]` or `/nowplaying [@user]` | Show Spotify activity |

**Aliases:** `$spoti`, `$np`, `/nowplaying`

**Features:**
- Hybrid command (works as prefix or slash command)
- Shows song title, artist, album
- Displays album artwork
- Links to Spotify track
- Query yourself or mention another user

---

### Quote Generator

Create shareable quote images from Discord messages.

| Command | Description |
|---------|-------------|
| `$quote [message_link\|text]` | Generate a quote image (style 1) |
| `$quote2 [message_link\|text]` | Generate a quote image (style 2) |

**Usage Methods:**
1. Reply to a message with `$quote`
2. Provide a message link: `$quote https://discord.com/channels/...`
3. Type custom text: `$quote Your quote here`

**Features:**
- Two different visual styles
- Avatar integration
- Handles mentions and emojis
- 150 character limit
- Cooldown: 10 seconds per user

**Example:**

![quote example](https://cdn.discordapp.com/attachments/808679873837137940/920026460234862643/unknown.png)

---

## Moderation

### Conversation Summaries

AI-powered conversation summaries for moderation (Google Gemini).

| Command | Description |
|---------|-------------|
| `$summarize <message_link> [count]` | Summarize conversation (Moderator only) |
| `$summary_stats` | View summary statistics (Owner only) |
| `$clear_summary_cache` | Clear summary cache (Owner only) |

**Features:**
- Analyze 1-500 messages (default: 100)
- 1-hour cache system
- Moderator-only access
- Cooldown: 30 seconds per user
- Skips bot messages

**Example:**
```
$summarize https://discord.com/channels/.../123456 50    # Summarize 50 messages
```

---

### Introduction Tracking

Prevent duplicate user introductions.

| Command | Description |
|---------|-------------|
| `$introtracker [on\|off\|status]` | Toggle introduction tracking (Owner only) |
| `$introstatus` | View introduction statistics (Owner only) |

**Features:**
- Tracks introductions for 30 days
- Deletes duplicate posts
- Sends friendly notification to users
- Exempt roles and specific users
- Redirects users to general chat

---

## Admin Commands

Owner-only utility commands.

| Command | Description |
|---------|-------------|
| `$note <content>` | Add a personal note |
| `$shownote <note_id>` | View a specific note |
| `$notes [limit]` | List your notes |
| `$deletenote <note_id>` | Delete a note |
| `$parrot <guild_id> <channel_id> <message>` | Send message to specific channel |
| `$mystats` | View bot guild statistics |

---

## Technical Details

**Tech Stack:**
- **Framework:** discord.py (Python)
- **Database:** PostgreSQL with asyncpg
- **AI/ML:** Google Gemini API
- **External APIs:** Spotify, WordReference
- **Deployment:** Docker-compatible

**Key Features:**
- Async/await throughout
- Connection pooling for database
- Caching systems for performance
- Rate limiting for external APIs
- Comprehensive error handling
- Detailed logging

---

## Setup & Configuration

### Environment Variables

Required environment variables:

```bash
BOT_TOKEN=your_discord_bot_token
DATABASE_URL=postgresql://user:password@host:port/database
GEMINI_API_KEY=your_gemini_api_key  # For conversation and summary features
PREFIX=$  # Command prefix (default: $)
```

### Installation

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up environment variables
4. Initialize database: `python database.py`
5. Run the bot: `python hablemos.py`

### Docker Deployment

```bash
docker build -t hablemos-bot .
docker run -d --env-file .env hablemos-bot
```

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## Links

- [Invite Bot](https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot%20applications.commands)
- [Spanish-English Learning Server](https://discord.gg/spanish-english)
- [Support/Issues](https://github.com/yourusername/hablemos-discordpy-bot/issues)

---

## License

This project is licensed under the MIT License.

---

**Bot created and maintained for the Spanish-English Learning Discord community** 🇪🇸 🇬🇧
