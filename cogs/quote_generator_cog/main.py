"""Quote generator — creates styled quote images from Discord messages."""
import logging
import tempfile
import time
from pathlib import Path
from re import sub

import demoji
from discord import File, Forbidden, HTTPException, NotFound
from discord.ext.commands import BucketType, command, cooldown

from base_cog import BaseCog
from cogs.quote_generator_cog.markdown import remove_markdown_from_message
from cogs.quote_generator_cog.quote_generator_helper.image_creator import (
    create_image,
)
from cogs.quote_generator_cog.quote_generator_helper.image_creator2 import (
    create_image2,
)
from cogs.utils.embeds import green_embed, red_embed, yellow_embed

from .config import FEATURE_KEY_EMOJI
from .emoji import replace_emoji_with_images, visual_length

logger = logging.getLogger(__name__)

MAX_QUOTE_LENGTH = 250
DEFAULT_AVATAR = "https://i.imgur.com/z9tOsSz.png"


def _get_img_url(url_identifier: str | None) -> str:
    """Get a high-res avatar URL, falling back to a default."""
    if url_identifier is None:
        return DEFAULT_AVATAR
    return str(url_identifier)[:-4] + '4096'


def _remove_custom_emoji(text: str) -> str:
    """Strip custom Discord emoji markup from text."""
    return sub(r"<:[A-Za-z0-9_]+:([0-9]+)>", '', text).replace("  ", " ")


def _strip_standard_emoji(text: str) -> str:
    """Strip standard Unicode emoji, truncate to 28 chars."""
    return demoji.replace(text, '')[:28]


def _has_font_safe_characters(text: str) -> bool:
    """Check if text contains only characters likely supported by common fonts."""
    for char in text:
        code = ord(char)
        if not (
            0x0020 <= code <= 0x007F or  # Basic Latin
            0x00A0 <= code <= 0x00FF or  # Latin-1 Supplement
            0x0100 <= code <= 0x017F or  # Latin Extended-A
            0x0180 <= code <= 0x024F or  # Latin Extended-B
            0x0300 <= code <= 0x036F     # Combining Diacritical Marks
        ):
            logger.debug("Unsupported character: %r (U+%04X)", char, code)
            return False
    return True


def _get_safe_username(user, guild=None) -> str:
    """Get a font-safe display name, falling back to the Discord username."""
    nick = getattr(user, 'nick', None)
    if guild is None or guild.get_member(user.id) is None or nick is None:
        username = user.display_name
    else:
        username = _strip_standard_emoji(nick)

    if len(username.strip()) <= 1 or not _has_font_safe_characters(username):
        username = user.name

    return username


def _resolve_mentions(content: str, mentions, role_mentions, channel_mentions, guild=None) -> str:
    """Replace raw Discord mention markup with human-readable names."""
    for user in mentions:
        member = guild.get_member(user.id) if guild else None
        display = '@' + (member.display_name if member else user.name)
        for pattern in (f'<@!{user.id}>', f'<@{user.id}>'):
            content = content.replace(pattern, display)
    for role in role_mentions:
        content = content.replace(f'<@&{role.id}>', f'@{role.name}')
    for ch in channel_mentions:
        content = content.replace(f'<#{ch.id}>', f'#{ch.name}')
    return content


async def _clean_message_content(content: str, mentions, role_mentions, channel_mentions, guild=None, *, db=None) -> str:
    """Strip emoji, markdown, and resolve mentions from message content."""
    emoji_enabled = await db.get_feature_setting(FEATURE_KEY_EMOJI) if db else False
    if emoji_enabled:
        content = replace_emoji_with_images(content)
    else:
        content = _remove_custom_emoji(content)
    content = remove_markdown_from_message(content)
    return _resolve_mentions(content, mentions, role_mentions, channel_mentions, guild)


def _parse_message_link(link: str) -> tuple[int, int, int] | None:
    """Parse a Discord message link into (guild_id, channel_id, message_id). Returns None if invalid."""
    parts = link.split('/')
    try:
        return int(parts[4]), int(parts[5]), int(parts[6])
    except (IndexError, ValueError):
        return None


class QuoteGenerator(BaseCog):
    """Create styled quote images from Discord messages."""

    async def _check_permissions(self, ctx) -> bool:
        """Check pause state, user ban, and channel ban. Sends error and returns False if blocked."""
        paused_until = await self.bot.db.get_bot_setting('quote_paused_until')
        if paused_until and paused_until > int(time.time()):
            await ctx.send(embed=yellow_embed("Quotes are temporarily paused. Try again later."))
            return False

        if await self.bot.db.is_quote_banned(ctx.author.id):
            await ctx.send(embed=red_embed("You are not allowed to use quote commands."))
            return False

        if await self.bot.db.is_quote_channel_banned(ctx.channel.id):
            await ctx.send(embed=red_embed("Quotes are not allowed in this channel."))
            return False

        return True

    async def _extract_quote_data(self, ctx, message) -> tuple[str, str, str] | None:
        """Extract (username, avatar_url, content) from a fetched message. Returns None if opted out."""
        if await self.bot.db.is_quote_opted_out(message.author.id):
            await ctx.send(embed=red_embed("This user has opted out of being quoted."))
            return None

        content = await _clean_message_content(
            message.content, message.mentions, message.role_mentions,
            message.channel_mentions, ctx.guild, db=self.bot.db,
        )
        username = _get_safe_username(message.author, ctx.guild)
        avatar = _get_img_url(message.author.avatar)
        return username, avatar, content

    async def _fetch_message_safe(self, ctx, channel, message_id):
        """Fetch a message, sending an error embed on failure. Returns the message or None."""
        try:
            return await channel.fetch_message(message_id)
        except NotFound:
            await ctx.send(embed=red_embed("That message was not found."))
        except Forbidden:
            await ctx.send(embed=red_embed("I don't have permission to read that message."))
        except HTTPException:
            logger.exception("Failed to fetch message %s", message_id)
            await ctx.send(embed=red_embed("Something went wrong fetching that message."))
        return None

    async def _parse_quote_input(self, ctx, user_input: tuple, command_name: str):
        """
        Parse quote input from a reply, message link, or freetext.
        Returns (user_nick, user_avatar, message_content) or None if an error was sent.
        """
        if not await self._check_permissions(ctx):
            return None

        is_reply = ctx.message.reference is not None

        if not user_input and not is_reply:
            await ctx.send(embed=red_embed(f"Please type `$help {command_name}` for info on correct usage."))
            return None

        # Detect bare message IDs (common mistake)
        if len(user_input) == 1 and user_input[0].isdigit() and not is_reply:
            await ctx.send(embed=red_embed(
                "That looks like a message ID. Please use a message link or reply instead. "
                f"See `$help {command_name}` for correct usage."
            ))
            return None

        # Reply to a message
        if is_reply:
            ref = ctx.message.reference
            channel = self.bot.get_channel(ref.channel_id)
            if channel is None:
                await ctx.send(embed=red_embed("I can't access that channel."))
                return None

            msg = await self._fetch_message_safe(ctx, channel, ref.message_id)
            if msg is None:
                return None
            return await self._extract_quote_data(ctx, msg)

        # Message link
        if len(user_input) == 1 and user_input[0].startswith("https://discord.com/channels/"):
            parsed = _parse_message_link(user_input[0])
            if parsed is None:
                await ctx.send(embed=red_embed("That doesn't look like a valid message link."))
                return None

            guild_id, channel_id, msg_id = parsed
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                await ctx.send(embed=red_embed("I can't access that server."))
                return None
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                await ctx.send(embed=red_embed("I can't access that channel."))
                return None

            msg = await self._fetch_message_safe(ctx, channel, msg_id)
            if msg is None:
                return None
            return await self._extract_quote_data(ctx, msg)

        # Freetext — user is quoting themselves
        content = await _clean_message_content(
            ' '.join(user_input), ctx.message.mentions, ctx.message.role_mentions,
            ctx.message.channel_mentions, ctx.guild, db=self.bot.db,
        )
        username = _get_safe_username(ctx.author, ctx.guild)
        avatar = _get_img_url(ctx.author.avatar)
        return username, avatar, content

    async def _generate_and_send(self, ctx, user_input: tuple, command_name: str, creator_fn) -> None:
        """Shared logic for quote and quote2 commands."""
        result = await self._parse_quote_input(ctx, user_input, command_name)
        if result is None:
            return

        user_nick, user_avatar, message_content = result

        if visual_length(message_content) > MAX_QUOTE_LENGTH:
            await ctx.send(embed=red_embed(
                f"Beep boop, I can't create an image. I'm limited to {MAX_QUOTE_LENGTH} characters."
            ))
            return

        # Generate image to a temp file to avoid race conditions
        img_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img_path = tmp.name
            creator_fn(user_nick, user_avatar, message_content, output_path=img_path)
            await ctx.send(file=File(img_path))
        except HTTPException:
            logger.exception("Failed to send quote image")
            await ctx.send(embed=red_embed("Something went wrong sending the image."))
        except Exception:
            logger.exception("Failed to generate quote image")
            await ctx.send(embed=red_embed("Something went wrong generating the image."))
        finally:
            if img_path:
                Path(img_path).unlink(missing_ok=True)

    @command(aliases=['q'])
    @cooldown(1, 10, type=BucketType.user)
    async def quote(self, ctx, *user_input):
        """
        Creates a quote image from a message link, reply, or your own text.

        Example usage:
        `$quote https://discord.com/channels/.../.../.../`
        `$quote todo es bronca y dolor`
        Or reply to a message with `$quote`
        """
        await self._generate_and_send(ctx, user_input, "quote", create_image)

    @command(aliases=['q2'])
    @cooldown(1, 10, type=BucketType.user)
    async def quote2(self, ctx, *user_input):
        """Creates a quote using the card style. Usage mirrors `$quote`."""
        await self._generate_and_send(ctx, user_input, "quote2", create_image2)

    @command()
    async def quoteme(self, ctx, toggle: str | None = None):
        """
        Manage your quote opt-out status.

        `$quoteme off` — opt out of being quoted by others
        `$quoteme on` — opt back in
        `$quoteme` — show current status
        """
        db = self.bot.db

        if toggle is None:
            opted_out = await db.is_quote_opted_out(ctx.author.id)
            if opted_out:
                await ctx.send(embed=yellow_embed(
                    "You are currently **opted out** of being quoted. Use `$quoteme on` to opt back in."
                ))
            else:
                await ctx.send(embed=green_embed(
                    "You are currently **opted in** to being quoted. Use `$quoteme off` to opt out."
                ))
            return

        toggle = toggle.lower()
        if toggle == "off":
            await db.quote_optout(ctx.author.id)
            await ctx.send(embed=green_embed(
                "You have opted out of being quoted. Others can no longer quote your messages."
            ))
        elif toggle == "on":
            success = await db.quote_optin(ctx.author.id)
            if success:
                await ctx.send(embed=green_embed("You have opted back in. Others can quote your messages again."))
            else:
                await ctx.send(embed=yellow_embed("You were already opted in."))
        else:
            await ctx.send(embed=red_embed("Usage: `$quoteme [on|off]`"))


async def setup(bot):
    await bot.add_cog(QuoteGenerator(bot))
    from cogs.quote_generator_cog.admin import QuoteAdminCog
    await bot.add_cog(QuoteAdminCog(bot))
