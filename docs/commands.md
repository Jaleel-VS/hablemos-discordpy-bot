# User Commands

Non-admin commands any server member can use. Owner/mod-only commands
live in [`admin.md`](./admin.md).

All prefix commands use the configured prefix (default `$`). Slash
commands are shown as `/name`.

> **Living-doc rule:** adding, removing, or renaming a user command
> must update this file in the same commit. See
> [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## Language League

See [`cogs/league.md`](./cogs/league.md) for the full feature.

| Command | Description |
|---------|-------------|
| `/league join` | Opt into the league. Also triggerable from the public "Join the League" button. |
| `/league leave` | Opt out of the league. |
| `/league view` | Show the current leaderboard. |
| `/league stats [@user]` | Show your league stats, or another member's. |

## Crossword

See [`cogs/crossword.md`](./cogs/crossword.md) for the full feature.

| Command | Description |
|---------|-------------|
| `$crossword [difficulty] [language]` / `$cw` | Start a crossword puzzle in the current channel. |
| `/crossword` | Slash version with dropdowns for difficulty and language. |
| `$cwl` / `$cwleaderboard [scope]` | Per-server crossword leaderboard. Scopes: `all` (default), `week`, `month`, or `<N>` days. |
| In-game: `quit` | Starter or mods-with-manage-messages can cancel the game. |
| In-game: `giveup` / `reveal` | Starter-only: end the game and show answers. |
| In-game: `!hint` | Reveal one random letter (max 2 per game). |

## Introductions & exchange posts

See [`cogs/introduce.md`](./cogs/introduce.md) for the full feature.

| Command | Description |
|---------|-------------|
| `/introduce` | Start the introduction flow (modal-based). Must be used in the configured command channel. |
| `$introduce` | Posts a persistent "Introduce Yourself" button in the command channel. |
| `/exchange delete` | Delete your own exchange-partner post. |
| `/exchange repost` | Repost your exchange post (cooldown applies). |

## Conjugation

See [`cogs/conjugation.md`](./cogs/conjugation.md) for the full feature.

| Command | Description |
|---------|-------------|
| `/conjugate [mode] [tense]` | Interactive Spanish verb conjugation practice. Modes: `learn`, `test`. Tenses: `presente`, `pretérito`, `imperfecto`, `futuro`, `condicional`, and more. |

## Conversation

See [`cogs/conversation.md`](./cogs/conversation.md) for the full feature.

| Command | Description |
|---------|-------------|
| `$conversation <category> [level] [language] [length]` / `$convo` | Generate an AI conversation for practice. Categories: `general`, `travel`, `food`, etc. Levels: `beginner`, `intermediate`, `advanced`. |

## Conversation Starter

See [`cogs/convo_starter.md`](./cogs/convo_starter.md) for the full feature.

| Command | Description |
|---------|-------------|
| `$topic [category]` / `$top` | Post a random bilingual discussion topic. Categories: `general`, `phil`, `would`, `other`. |
| `$lst` / `$list` | List available topic categories. |

## Dictation

See [`cogs/dictation.md`](./cogs/dictation.md) for the full feature.

| Command | Description |
|---------|-------------|
| `/dictation <language> <level>` | Audio listening exercise. Listen to a clip and type what you hear. Scored 0–4. |

## Dictionary

See [`cogs/dictionary.md`](./cogs/dictionary.md) for the full feature.

| Command | Description |
|---------|-------------|
| `$define <word> [source]` / `$def` | Look up a word across multiple dictionary sources (Merriam-Webster, Wiktionary, Oxford, Cambridge). |

## General

See [`cogs/general.md`](./cogs/general.md) for the full feature.

| Command | Description |
|---------|-------------|
| `/help [category]` | View all commands or a specific cog's commands. |
| `/info` | Show bot info: uptime, guilds, latency, code stats. |
| `/ping` | Latency check. |
| `$invite` | Post the bot invite link. |

## Hangman

See [`cogs/hangman.md`](./cogs/hangman.md) for the full feature.

| Command | Description |
|---------|-------------|
| `$hangman [category]` / `$hm` / `$hang` | Start a Spanish hangman game. Categories: `animales`, `profesiones`, `ciudades`. Type letters to guess, `quit` to exit (starter only). |

## Higher or Lower

See [`cogs/hol.md`](./cogs/hol.md) for the full feature.

| Command | Description |
|---------|-------------|
| `$hol` / `$higherloower` | Guess which search term is more popular. Interactive button game. |

## Practice

See [`cogs/practice.md`](./cogs/practice.md) for the full feature.

| Command | Description |
|---------|-------------|
| `/practice [mode] [due_only]` | Cloze sentence practice with spaced repetition (FSRS). Modes: `learn`, `test`. |
| `/practice_stats` | Show your practice stats: total cards, new/learning/review counts, cards due. |

## Practice Test (Prototype)

See [`cogs/practice_test.md`](./cogs/practice_test.md) for the full feature.

| Command | Description |
|---------|-------------|
| `$practice` | Prototype Components V2 practice flow (hardcoded sample cards, no persistence). |

## Quote Generator

See [`cogs/quote_generator.md`](./cogs/quote_generator.md) for the full feature.

| Command | Description |
|---------|-------------|
| `$quote <message_link>` / `$q` | Generate a styled quote image from a message (style 1). |
| `$quote2 <message_link>` / `$q2` | Style 2 quote image. |
| `$quote3 <message_link>` / `$q3` | Style 3 quote image. |
| `$quotemulti <message_links...>` / `$qm` | Multi-message quote (up to 10 messages). |

## Spotify

See [`cogs/spotify.md`](./cogs/spotify.md) for the full feature.

| Command | Description |
|---------|-------------|
| `/nowplaying [@user]` | Show what you (or another user) are listening to on Spotify. Displays track, artist, album, progress bar, and album art. |

## Vocab

See [`cogs/vocab.md`](./cogs/vocab.md) for the full feature.

| Command | Description |
|---------|-------------|
| `/vocab add` | Add a personal vocab note (modal form). |
| `/vocab list [language] [limit]` | List your notes (default 10, max 50). |
| `/vocab search <query>` | Search your notes by word or translation. |
| `/vocab delete <note_id>` | Delete a note by ID. |
| `/vocab export [language]` | Export notes as CSV. |
| `/vocab stats` | Show note counts by language. |

## Conventions

- Most commands that post user content use **ephemeral responses** for
  errors so the channel stays clean.
- User-facing commands have per-user or per-channel cooldowns to
  prevent spam.
- Slash commands scoped to a specific guild sync instantly; global
  slash commands are synced manually via `$sync`.
