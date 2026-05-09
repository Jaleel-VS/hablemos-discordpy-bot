# Quote Generator (`quote_generator_cog`)

Creates styled quote images from Discord messages.

## Overview

The quote generator cog turns Discord messages into shareable quote
images with user avatars, names, timestamps, and message content. It
supports multiple visual styles and handles emojis, attachments, and
reactions.

## Commands

| Command | Description | Permissions | Cooldown |
|---------|-------------|-------------|----------|
| `$quote <message_link>` / `$q` | Generate a quote image from a message. Uses style 1 (default). | None | 5s/user |
| `$quote2 <message_link>` / `$q2` | Style 2 (alternate layout). | None | 5s/user |
| `$quote3 <message_link>` / `$q3` | Style 3 (alternate layout). | None | 5s/user |
| `$quotemulti <message_links...>` / `$qm` | Multi-message quote (up to 10 messages). | None | 10s/user |

## Configuration

| Constant | Location | Default | Purpose |
|---------|----------|---------|---------|
| `FEATURE_KEY_EMOJI` | `cogs/quote_generator_cog/config.py` | Custom emoji for feature toggle | Optional. |

## Implementation notes

- The cog uses Pillow (PIL) to render images.
- Three different image creators (`image_creator.py`,
  `image_creator2.py`, `image_creator3.py`) provide the styles.
- Emojis are replaced with images using `replace_emoji_with_images` (in
  `emoji.py`).
- Markdown is stripped from message content (see `markdown.py` /
  `remove_markdown_from_message`).
- Multi-message quotes are rendered as a conversation thread (see
  `image_creator_multi.py`).

## Related

- [`./general.md`](./general.md) — other utility commands.
