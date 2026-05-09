# Vocab (`vocab_cog`)

Personal vocabulary note-taking system.

## Overview

The vocab cog lets users save vocabulary notes (word, translation,
language) privately via slash commands. Notes are stored per-user in the
database and can be exported as CSV. All interactions are ephemeral
(only visible to the user).

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `/vocab add` | Open a modal to add a vocab note (word, translation, language). | None |
| `/vocab list [language] [limit]` | List your notes (filtered by language, default 10, max 50). | None |
| `/vocab search <query>` | Search your notes by word or translation. | None |
| `/vocab delete <note_id>` | Delete a note by ID. | None |
| `/vocab export [language]` | Export notes as CSV (filtered by language). | None |
| `/vocab stats` | Show note counts by language. | None |

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `vocab_notes` | `VocabMixin` | User vocab notes. Columns: `id`, `user_id`, `word`, `translation`, `language`, `created_at`. |

See [`../database.md`](../database.md) for query methods (in
`VocabMixin`).

## Implementation notes

- All slash commands respond ephemerally (only visible to the user).
- The `/vocab add` command uses a `VocabNoteModal` (in the main cog
  file) to collect input.
- CSV export is generated in-memory and sent as a Discord file
  attachment.

## Related

- [`./dictionary.md`](./dictionary.md) — dictionary lookups.
- [`./practice.md`](./practice.md) — spaced repetition practice.
