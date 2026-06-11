# User Commands

Non-admin commands any server member can use. Owner/mod-only commands
live in [`admin.md`](./admin.md).

All prefix commands use the configured prefix (default `$`). Slash
commands are shown as `/name`.

> **Living-doc rule:** adding, removing, or renaming a user command
> must update this file in the same commit. See
> [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## World Cup

| Command | Description |
|---------|-------------|
| `/worldcup` | Manage your World Cup team role. Shows a menu to pick a team (paginated select) or remove your current team. Remove button only appears if you already have a team role. Logs all changes to `#world-cup-log`. |
| `/wcpredict set` | Save (or change) your private prediction for who will win the World Cup. Locks at the configured deadline. See [`cogs/wcpredict.md`](./cogs/wcpredict.md). |
| `/wcpredict view` | Show your current prediction (ephemeral). |
| `/wcpredict leaderboard` | Pre-grading: per-team pick distribution. After an admin records the champion: full standings with ✅/❌ per user. |
| `$wcfixtures` (alias `$wcf`) | Paginated embed of all 104 World Cup 2026 fixtures (17 pages: Groups A–L, R32, R16, QF, Semis/Final). Each page shows flag emojis, kick-off time (ET), venue and city. Optional argument jumps to a specific section — e.g. `$wcf A`, `$wcf brasil`, `$wcf alemania`, `$wcf r32`, `$wcf semi`. Accepts English and Spanish team names. |
| `$wcbet` | World Cup match betting with virtual coins at **real DraftKings odds**. Posts a public button; clicking opens **your own** ephemeral betting panel (Components V2 stepper): opt in once for 10,000 coins, pick one of today's group-stage matches (until kickoff), choose an outcome (priced buttons, e.g. `South Africa · 8.50`), then a stake from a select whose options show the exact payout. Correct bets pay `floor(stake × odds)`; one editable bet per match; +500 daily allowance claimed lazily. **Currently gated for testing** — the public command is disabled; the owner-only `$wcbettest` runs the identical flow. See [`cogs/wcbet.md`](./cogs/wcbet.md). |

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

## Moderation

| Command | Description |
|---------|-------------|
| `$nogif @user <duration>` | Temporarily block a member from sending GIFs/embeds by assigning the `Sin GIFs` role. Duration format: `30s`, `10m`, `2h`, `1d` (max 30 days). Requires `Manage Roles`. The bot creates the role and sets `embed_links=False` channel overwrites automatically on first use. Restriction survives bot restarts. |
| `$ungif @user` | Lift a no-GIF restriction early. Requires `Manage Roles`. |

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
