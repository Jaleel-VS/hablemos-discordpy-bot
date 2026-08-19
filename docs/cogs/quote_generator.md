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
| `$quotem [count]` / `$qm` | Multi-message conversation quote. Must be used as a reply; captures the replied message plus up to `count` (1–5) earlier messages via the reply chain or channel history. | None | 15s/user |
| `$quoteme [on\|off]` | Manage your own quote opt-out status via text. `off` opts out, `on` opts back in, no arg shows status. | None | None |
| `$q0` / `$quoteopt` | Button-based opt in/out panel — the intuitive version of `$quoteme`. Shows your current status with **Opt in** / **Opt out** buttons. | None | None |

## Configuration

| Constant | Location | Default | Purpose |
|---------|----------|---------|---------|
| `FEATURE_KEY_EMOJI` | `cogs/quote_generator_cog/config.py` | Custom emoji for feature toggle | Optional. |

## Implementation notes

- Single-message styles (`$quote`, `$quote2`, `$quote3`) render via
  imgkit/wkhtmltoimage from HTML templates (`image_creator.py`,
  `image_creator2.py`, `image_creator3.py`). Emoji in these are inlined as
  HTML `<img>` tags by `replace_emoji_with_images` (in `emoji.py`), and
  their length cap uses `visual_length`. A regex match may span several
  standalone emoji (e.g. `😍💋`), so the run is split into clusters and one
  `<img>` is emitted per cluster — Twemoji serves each standalone emoji as a
  separate file, and only joins codepoints with `-` for ZWJ/flag sequences
  (joining `😍💋` into `1f60d-1f48b.png` would 404). `_split_emoji_clusters`
  keeps a base emoji joined to its skin-tone modifier, keycap combiner
  (`1️⃣`), and tag-sequence characters (flag subdivisions, e.g. the England
  flag) — those Twemoji files are also joined with `-`, so splitting on them
  would 404 or render the wrong (untoned/base) image.
- The multi-message conversation quote (`$quotem`) renders with **Pillow**
  (`image_creator_multi.py`), following the super-sample → LANCZOS
  downsample pattern documented in
  [`../architecture.md`](../architecture.md#image-rendering-pillow) (render
  at `S = SCALE * OUTPUT_SCALE = 6`, export at `OUTPUT_SCALE`). It draws a
  Discord dark-theme card with circular avatars, bold name lines, inline
  emoji, and word-wrapped body text.
  - Emoji are handled as structured tokens via `tokenize_for_render`
    (text runs vs. emoji PNG URLs — Twemoji for Unicode, the Discord CDN
    for custom `<:name:id>` emoji), and its length cap uses
    `render_visual_length`. `_clean_message_content(..., for_render=True)`
    preserves raw emoji markup instead of emitting HTML `<img>` tags.
- Emoji rendering is gated by the `quote_emoji` feature flag (toggle with
  `$quoteadmin emoji`), which seeds to **enabled**. When disabled,
  `_clean_message_content` strips *both* custom and Unicode emoji via
  `_strip_all_emoji` — otherwise bare Unicode emoji leak into the renderer
  and draw as missing-glyph boxes (tofu), since the quote fonts have no
  emoji coverage.
- Markdown is stripped from message content (see `markdown.py` /
  `remove_markdown_from_message`).
- **Opt-out handling.** Users can opt out of being quoted
  (`is_quote_opted_out`). Opting out blocks *others* from quoting them, but
  a user can always quote **themselves** — the single-message paths
  (`_extract_quote_data`, context-menu `_generate_from_message`) skip the
  opt-out check when the message author is the invoker. For `$quotem`, if
  any message in the collected chain belongs to an opted-out user *other
  than the invoker*, the command aborts with an error rather than dropping
  that turn (dropping it would produce a disjointed quote).
  - Opt-out status is toggled two ways: `$quoteme on|off` (text) and `$q0`
    (an ephemeral button panel, `QuoteOptView` in `views.py`). The view is
    per-invoker (`interaction_check` locks it to the caller), times out
    after `VIEW_TIMEOUT` seconds, and disables the button matching the
    current status so the active state is obvious.

## Related

- [`./general.md`](./general.md) — other utility commands.
