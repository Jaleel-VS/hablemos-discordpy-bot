# Database (`database_cog`)

Owner-only note management — a simple key-value store for bot owner
memos.

## Overview

The database cog provides a set of commands for adding, viewing,
listing, and deleting notes. Notes are stored in the `notes` table (see
[`../database.md`](../database.md)) and are keyed by user ID. This is a
personal scratchpad for the bot owner, not a general-purpose note system
for all users.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `$note <content>` / `$addnote` | Add a new note. Returns the note ID. | Owner-only |
| `$shownote <id>` / `$getnote` / `$readnote` | View a specific note by ID. | Owner-only |
| `$notes [limit]` / `$mynotes` / `$listnotes` | List your recent notes (default 5, max 20). | Owner-only |
| `$deletenote <id>` / `$delnote` / `$removenote` | Delete a note you own. | Owner-only |

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `notes` | `NotesMixin` | Stores user notes. Columns: `id`, `user_id`, `username`, `content`, `created_at`. |

See [`../database.md`](../database.md) for query methods (in
`NotesMixin`).

## Implementation notes

- All commands are owner-only via `@is_owner()` decorator.
- The `username` column is informational only (helps when browsing the
  DB directly); the `user_id` is the primary key.
- Notes are plain text (no markdown rendering or rich embeds).

> TODO: Consider adding multi-user support if other bot admins need a
> shared scratchpad (currently, only the bot owner can use these
> commands, though anyone's ID could theoretically be stored).
