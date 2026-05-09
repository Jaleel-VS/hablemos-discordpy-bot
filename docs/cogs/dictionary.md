# Dictionary (`dictionary_cog`)

Multi-source dictionary lookup for Spanish and English words.

## Overview

The dictionary cog provides a `$define` command that looks up words
across multiple sources: Merriam-Webster, Wiktionary, Oxford, and
Cambridge. Users can specify a source or let the bot pick automatically.

## Commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$define <word> [source]` / `$def` | Look up a word. Sources: `web` (Merriam-Webster), `wiktionary`, `oxford` / `oxf`, `cambridge`. Defaults to all sources. | None | 10s/user |

## Implementation notes

- Each source has a scraper function (in the main cog file) that
  extracts definitions from the source's HTML.
- The cog uses `aiohttp` + `BeautifulSoup` for scraping.
- Results are returned as `DefinitionResult` dataclass instances.
- If no definitions found or scraping fails, an error embed is shown.

## Related

- [`./vocab.md`](./vocab.md) — personal vocab note-taking.
- [`./practice.md`](./practice.md) — spaced repetition practice.
