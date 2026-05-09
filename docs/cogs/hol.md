# Higher or Lower (`hol_cog`)

Guess which search term is more popular.

## Overview

The higher-or-lower cog is a game where players guess whether a mystery
search term gets more or fewer monthly searches than a known term. The
game continues until the player guesses wrong or times out. Streak is
tracked per session.

The word pool is pre-loaded from `cogs/hol_cog/data.py` and includes
search volume data.

## Commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$hol` / `$higherloower` | Start a higher-or-lower game (interactive buttons). Only works in configured HOL channels. | None | 5s/user |

## Configuration

| Constant | Location | Default | Purpose |
|---------|----------|---------|---------|
| `HOL_CHANNEL_IDS` | `cogs/hol_cog/config.py` | `[]` | Channel IDs where the game is allowed. Empty list = works everywhere. |
| `TIMEOUT` | `cogs/hol_cog/main.py` | 30 seconds | How long players have to make a guess before timeout. |

## Gameplay

1. User runs `$hol`.
2. Bot shows two search terms: one with known volume, one mystery.
3. User clicks "Higher" or "Lower" button.
4. If correct:
   - Streak increments.
   - Mystery term becomes the new known term.
   - A new mystery term is picked (not seen this session).
   - New round posted with "Continue" button.
5. If wrong or timeout:
   - Game ends, final streak shown.

## Implementation notes

- The `pick_pair()` function (in `data.py`) picks two terms from the
  pool. Avoids duplicates within a session via `self.seen`.
- The `GameView` class provides "Higher" and "Lower" buttons (and a
  "Continue" button between rounds).
- If the player times out, the `on_timeout` callback posts the timeout
  result automatically.

## Related

- [`./crossword.md`](./crossword.md) — another game with timeout logic.
- [`./hangman.md`](./hangman.md) — another word game.
