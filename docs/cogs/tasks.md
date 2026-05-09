# Tasks (`tasks_cog`)

Admin task tracking with interactive Discord embeds.

## Overview

The tasks cog provides a kanban-style task board for server admins.
Tasks are stored in the database and posted to a configured tasks
channel as interactive embeds with dropdowns for status and assignment.

Key features:

- **Create tasks** via a modal form.
- **List/board views** for all tasks or filtered subsets.
- **Interactive embeds** with status and assignee dropdowns (persistent
  across restarts).
- **Delete tasks** via command (removes the embed + DB row).

## Commands

All commands are in the `/task` group and require `manage_guild`
permission.

| Command | Description |
|---------|-------------|
| `/task create` | Open a modal form to create a new task. |
| `/task list [status] [assignee]` | List tasks (filtered by status/assignee). Works in tasks channel or its category. |
| `/task board` | Show a kanban-style board with all tasks grouped by status. |
| `/task delete <task_id>` | Delete a task by ID (removes embed + DB row). |

## Configuration

| Constant / Env Var | Location | Default | Purpose |
|--------------------|----------|---------|---------|
| `TASKS_CHANNEL_ID` | `cogs/tasks_cog/config.py` | (baked-in) | Channel where task embeds are posted. |
| `TASKS_CATEGORY_ID` | `cogs/tasks_cog/config.py` | (baked-in) | Category containing read-only task archive channels. Commands work here too. |
| `STATUSES` | `cogs/tasks_cog/config.py` | `{backlog, todo, in_progress, review, done}` | Available task statuses (emoji, label, color). |
| `STATUS_CHOICES` | `cogs/tasks_cog/config.py` | Derived from `STATUSES` | Used for slash command autocomplete. |

## Database tables

| Table | Owns | Description |
|-------|------|-------------|
| `tasks` | `TasksMixin` | Task records. Columns: `id`, `guild_id`, `title`, `description`, `status`, `assignee_ids` (array), `message_id`, `created_at`, `updated_at`. |

See [`../database.md`](../database.md) for query methods (in
`TasksMixin`).

## Persistent views

Task embeds have interactive components with custom IDs like
`task_status:<task_id>` and `task_assign:<task_id>`. These are handled
dynamically in `on_interaction` rather than pre-registering a view per
task (since task IDs are unbounded).

## Implementation notes

- The `/task create` modal has fields for title, description, and
  initial status. After submission, the task is saved to the DB and
  posted to the tasks channel as an interactive embed.
- The `TaskView` class (in `views.py`) provides dropdowns for status and
  assignment. Updates are written to the DB and the embed is edited in
  place.
- The `/task board` command shows all tasks grouped by status in
  separate embeds (one per status).

## Related

- [`../commands.md`](../commands.md) — user command reference.
- [`./admin.md`](./admin.md) — other admin-only features.
