# Spotify (`spotify_cog`)

Now-playing command — shows what a user is listening to on Spotify.

## Overview

The spotify cog provides a `/nowplaying` command that fetches a user's
Spotify activity from Discord's presence API and displays it as a rich
embed with album art, track progress, and a dynamically extracted accent
color (mimicking Spotify's design).

## Commands

| Command | Description | Permissions |
|---------|-------------|-------------|
| `/nowplaying [@user]` | Show what you (or another user) are listening to on Spotify. Displays track, artist, album, progress bar, and album art. | None |

## Configuration

| Constant | Location | Default | Purpose |
|---------|----------|---------|---------|
| `SPOTIFY_EMOJI` | `cogs/spotify_cog/config.py` | `<:spotify:...>` | Custom Spotify emoji (falls back to 🎵 if not found). |

## Implementation notes

### Color extraction

The cog extracts a dominant color from the album art to use as the embed
accent color. Algorithm:

1. Fetch album art URL from Spotify activity.
2. Quantize image to 16 colors (Pillow's `MEDIANCUT`).
3. Score each color based on:
   - **Chroma** (colorfulness) — weighted 4.92×.
   - **Darkness** (1 - luminance) — weighted 1.41×.
   - **Dominance** (area coverage) — weighted 0.79×.
4. Skip near-gray colors (low saturation).
5. Boost saturation and cap brightness in HSV space for white text
   contrast.

Falls back to Spotify green (`#1ED760`) if extraction fails.

### Progress bar

The cog renders a text-based progress bar using Unicode block characters
(▬ for filled, ─ for empty). Timestamps are formatted as `MM:SS`.

## Related

- [`./general.md`](./general.md) — other user-facing utility commands.
