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

## Other cogs

> TODO: commands for the cogs below still need to be documented. Each
> cog gets a row here and a deep-dive under [`cogs/`](./cogs/).

- `ask_cog`
- `conjugation_cog`
- `conversation_cog`
- `convo_starter_cog`
- `dictation_cog`
- `dictionary_cog`
- `general_cog`
- `hangman_cog`
- `hol_cog`
- `intro_cog` (distinct from `introduce_cog`)
- `practice_cog`
- `practice_test_cog`
- `quote_generator_cog`
- `spotify_cog`
- `summary_cog`
- `tasks_cog`
- `vocab_cog`

## Conventions

- Most commands that post user content use **ephemeral responses** for
  errors so the channel stays clean.
- User-facing commands have per-user or per-channel cooldowns to
  prevent spam.
- Slash commands scoped to a specific guild sync instantly; global
  slash commands are synced manually via `$sync`.
