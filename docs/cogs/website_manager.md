# Website Manager (`website_manager_cog`)

Slash command for managing companion website resources (podcasts, videos,
etc.) via an API.

## Overview

This cog provides a `/manage` slash command that opens an ephemeral UI
panel for adding/editing/deleting content on the companion website. The
panel is permission-gated (bot owner or users with `manage_messages`).
It interacts with the website API via HTTP calls — the bot does not
store any website content locally.

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `/manage` | Open the website management panel (ephemeral). | Bot owner or `manage_messages` |

## Configuration

| Env Var | Location | Default | Purpose |
|---------|----------|---------|---------|
| `WEBSITE_API_URL` | Root `config.py` | (baked-in) | Base URL of the companion website API. |

## Implementation notes

- The cog uses a custom `WebsiteAPIClient` (in `api.py`) to communicate
  with the website API. The client is created per-cog instance and
  closed on cog unload.
- The UI is a `MainManageView` (in `views.py`) that shows buttons/selects
  for different resource types.
- All interactions are ephemeral (only visible to the user who ran the
  command).

> TODO: Document the full panel flow, API endpoints, and resource types
> once the companion website is deployed.
