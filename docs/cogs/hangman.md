# Hangman (`hangman_cog`)

Classic hangman game for Spanish vocabulary practice.

## Overview

The hangman cog provides an in-channel word-guessing game with three
categories: animals, professions, and cities. Players type letters to
guess; the game auto-exits after 45 seconds of inactivity.

## Commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$hangman [category]` / `$hm` / `$hang` | Start a hangman game. Categories: `animales` (default, 199 words), `profesiones` (141 words), `ciudades` (49 words). Type letters to guess, `quit` to exit (starter only). | None | 30s/channel |

## Gameplay

1. User runs `$hangman [category]`.
2. Bot posts the word as underscores + hangman art.
3. Players type single letters. The bot checks each message:
   - Correct letter → revealed in word, art doesn't change.
   - Wrong letter → art progresses (6 wrong guesses = game over).
4. Game ends when:
   - Word fully guessed (win).
   - 6 wrong guesses (loss).
   - Timeout (45s inactivity).
   - Starter types `quit`.

## Implementation notes

- The `Hangman` class (in `hangman.py`) tracks game state (word,
  revealed letters, wrong guesses, art).
- Word pool is loaded from `hangman_help.py` (`get_word(category)`).
- One game per channel; enforced via `self.active_games` dict.
- The `on_message` listener checks every message in active game channels
  and delegates to the game instance.
- Cleanup is automatic on game end.

## Related

- [`./hol.md`](./hol.md) — another word game.
- [`./crossword.md`](./crossword.md) — another game with timeout logic.
