from cogs.quote_generator_cog.quote_generator_helper.image_creator import dir_path, create_image
from cogs.quote_generator_cog.quote_generator_helper.image_creator2 import dir_path as dir_path2, create_image2
from base_cog import BaseCog

from re import sub
from os import remove
import logging
import time

logger = logging.getLogger(__name__)

from discord.ext.commands import command, cooldown, BucketType
from discord import File
import demoji


def get_img_url(url_identifier: str):
    if url_identifier is None:  # user doesn't have a profile picture
        return "https://i.imgur.com/z9tOsSz.png"
    return str(url_identifier)[:-4] + '4096'


def remove_emoji_from_message(message):  # for custom emojis
    return sub("<:[A-Za-z0-9_]+:([0-9]+)>", '', message).replace("  ", " ")


def give_emoji_free_text(text: str) -> str:  # for standard emojis
    result = demoji.replace(text, '')[:28]
    logger.info(f"give_emoji_free_text: input={text!r}, output={result!r}")
    return result


def has_font_safe_characters(text: str) -> bool:
    """
    Check if text contains only characters likely supported by common fonts.
    Covers Basic Latin, Latin Extended, common punctuation, and accented characters.
    """
    for char in text:
        code = ord(char)
        # Allow: Basic Latin, Latin-1 Supplement, Latin Extended-A/B, spacing/punctuation
        if not (
            0x0020 <= code <= 0x007F or  # Basic Latin (ASCII printable)
            0x00A0 <= code <= 0x00FF or  # Latin-1 Supplement (accents like é, ñ, ü)
            0x0100 <= code <= 0x017F or  # Latin Extended-A
            0x0180 <= code <= 0x024F or  # Latin Extended-B
            0x0300 <= code <= 0x036F     # Combining Diacritical Marks
        ):
            logger.info(f"Unsupported character found: {char!r} (U+{code:04X})")
            return False
    return True


def get_safe_username(user, server=None):
    """
    Get a safe username that handles special characters and emojis.
    Falls back to Discord username if stripped nickname is <= 1 character.
    """
    logger.info(
        f"get_safe_username called: user.id={user.id}, user.name={user.name!r}, "
        f"user.display_name={user.display_name!r}, user.nick={getattr(user, 'nick', None)!r}, "
        f"server={server}"
    )

    # If user has no nickname or not in server, use display_name
    nick = getattr(user, 'nick', None)
    if server is None or server.get_member(user.id) is None or nick is None:
        username = user.display_name
        logger.info(f"Using display_name path: username={username!r}")
    else:
        username = give_emoji_free_text(nick)
        logger.info(f"Using nick path: raw nick={nick!r}, after emoji strip={username!r}")

    # If stripped username is too short (1 char or less), use Discord username
    if len(username.strip()) <= 1:
        logger.info(f"Username too short ({len(username.strip())} chars), falling back to user.name={user.name!r}")
        username = user.name

    # If username contains characters unsupported by fonts, fall back to Discord username
    if not has_font_safe_characters(username):
        logger.info(f"Username contains unsupported characters, falling back to user.name={user.name!r}")
        username = user.name

    logger.info(f"Final username: {username!r}")
    return username


async def get_html_css_info(channel, message_id, server, message=None):
    if message is None:
        message = await channel.fetch_message(message_id)
    user = message.author
    message_content = remove_emoji_from_message(message.content)

    # Replace mentions (<@id>, <@!id>), role mentions (<@&id>) and channel mentions (<#id>)
    # with human readable forms so the generated image shows names instead of raw IDs.
    # Users
    for mentioned_user in message.mentions:
        member = server.get_member(mentioned_user.id) if server else None
        display = '@' + (member.display_name if member else mentioned_user.name)
        for pattern in (f'<@!{mentioned_user.id}>', f'<@{mentioned_user.id}>'):
            if pattern in message_content:
                message_content = message_content.replace(pattern, display)
    # Roles
    for role in message.role_mentions:
        pattern = f'<@&{role.id}>'
        if pattern in message_content:
            message_content = message_content.replace(pattern, f'@{role.name}')
    # Channels
    for ch in message.channel_mentions:
        pattern = f'<#{ch.id}>'
        if pattern in message_content:
            message_content = message_content.replace(pattern, f'#{ch.name}')

    user_nick = get_safe_username(user, server)

    user_avatar = get_img_url(user.avatar)

    return user_nick, user_avatar, message_content


class QuoteGenerator(BaseCog):
    def __init__(self, bot) -> None:
        super().__init__(bot)

    async def _parse_quote_input(self, ctx, user_input, command_name):
        """
        Parse quote input from a reply, message link, or freetext.
        Returns (user_nick, user_avatar, message_content) or None if an error was sent.
        """
        # Check if quotes are paused
        paused_until = await self.bot.db.get_bot_setting('quote_paused_until')
        if paused_until and paused_until > int(time.time()):
            await ctx.send("Quotes are temporarily paused. Try again later.")
            return None

        # Check if the invoking user is banned
        if await self.bot.db.is_quote_banned(ctx.author.id):
            await ctx.send("You are not allowed to use quote commands.")
            return None

        # Check if the channel is banned
        if await self.bot.db.is_quote_channel_banned(ctx.channel.id):
            await ctx.send("Quotes are not allowed in this channel.")
            return None

        is_message_reply = ctx.message.reference is not None

        if len(user_input) == 0 and not is_message_reply:
            await ctx.send(f"Please type `$help {command_name}` for info on correct usage")
            return None

        if len(user_input) == 1 and len(user_input[0]) == 18 and user_input[0].isdigit() and not is_message_reply:
            await ctx.send(
                f"You tried to use a message_id. Please use a link or just a regular message. "
                f"See `$help {command_name}` for correct usage")
            return None

        if is_message_reply:
            message_id = ctx.message.reference.message_id
            guild_id = ctx.message.reference.guild_id
            channel_id = ctx.message.reference.channel_id
            server = self.bot.get_guild(guild_id)
            if server is None:
                logger.warning(f"Could not find server with ID {guild_id}")
            channel = self.bot.get_channel(channel_id)

            # Check if the quoted message's author has opted out
            try:
                target_msg = await channel.fetch_message(message_id)
                if await self.bot.db.is_quote_opted_out(target_msg.author.id):
                    await ctx.send("This user has opted out of being quoted.")
                    return None
            except Exception:
                target_msg = None  # Let get_html_css_info handle fetch errors

            return await get_html_css_info(channel, message_id, server, message=target_msg)

        elif len(user_input) == 1 and user_input[0].startswith("https://discord.com/channels/"):
            link = user_input[0].split('/')
            server_id = int(link[4])
            channel_id = int(link[5])
            msg_id = int(link[6])

            server = self.bot.get_guild(server_id)
            if server is None:
                await ctx.send("I can't access this server")
                return None
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                await ctx.send("I can't access this channel")
                return None

            # Check if the quoted message's author has opted out
            try:
                target_msg = await channel.fetch_message(msg_id)
                if await self.bot.db.is_quote_opted_out(target_msg.author.id):
                    await ctx.send("This user has opted out of being quoted.")
                    return None
            except Exception:
                target_msg = None  # Let get_html_css_info handle fetch errors

            return await get_html_css_info(channel, msg_id, server, message=target_msg)

        else:
            message_content = remove_emoji_from_message(' '.join(user_input))
            for mentioned_user in ctx.message.mentions:
                member = ctx.guild.get_member(mentioned_user.id) if ctx.guild else None
                display = '@' + (member.display_name if member else mentioned_user.name)
                for pattern in (f'<@!{mentioned_user.id}>', f'<@{mentioned_user.id}>'):
                    if pattern in message_content:
                        message_content = message_content.replace(pattern, display)
            for role in ctx.message.role_mentions:
                pattern = f'<@&{role.id}>'
                if pattern in message_content:
                    message_content = message_content.replace(pattern, f'@{role.name}')
            for ch in ctx.message.channel_mentions:
                pattern = f'<#{ch.id}>'
                if pattern in message_content:
                    message_content = message_content.replace(pattern, f'#{ch.name}')
            user_nick = get_safe_username(ctx.author, ctx.guild)
            user_avatar = get_img_url(ctx.author.avatar)
            return user_nick, user_avatar, message_content

    @command(aliases=['q', ])
    @cooldown(1, 10, type=BucketType.user)
    async def quote(self, ctx, *user_input):
        """
        (still testing, please report any errors or suggestions)
        Creates a quote using a **message url**, **your own message** or **replying to a message**.
        Images and custom emojis won't show up and there's a limit to 250 characters.

        Example usage:
        `$quote https://discord.com/channels/731403448502845501/808679873837137940/916938526329798718`
        (creates a quote using a specific message)
        `$quote todo es bronca y dolor`
        (creates a quote using your own message)
        """
        result = await self._parse_quote_input(ctx, user_input, "quote")
        if result is None:
            return

        user_nick, user_avatar, message_content = result

        if len(message_content) > 250:
            return await ctx.send("Beep boop, I can't create an image. I'm limited to 250 characters")

        generated_url = create_image(user_nick, user_avatar, message_content)
        await ctx.send(file=File(generated_url))
        remove(f"{dir_path}/picture.png")

    @command(aliases=['q2', ])
    @cooldown(1, 10, type=BucketType.user)
    async def quote2(self, ctx, *user_input):
        """
        Creates a quote using the new card style. Usage mirrors `$quote`.
        """
        result = await self._parse_quote_input(ctx, user_input, "quote2")
        if result is None:
            return

        user_nick, user_avatar, message_content = result

        if len(message_content) > 250:
            return await ctx.send("Beep boop, I can't create an image. I'm limited to 250 characters")

        generated_url = create_image2(user_nick, user_avatar, message_content)
        await ctx.send(file=File(generated_url))
        remove(f"{dir_path2}/picture2.png")


    @command()
    async def quoteme(self, ctx, toggle: str = None):
        """
        Manage your quote opt-out status.

        `$quoteme off` — opt out of being quoted by others
        `$quoteme on` — opt back in
        `$quoteme` — show current status

        This only affects others quoting your messages (via reply or link).
        You can always quote your own text with `$quote <text>`.
        """
        db = self.bot.db

        if toggle is None:
            opted_out = await db.is_quote_opted_out(ctx.author.id)
            if opted_out:
                await ctx.send("You are currently **opted out** of being quoted. Use `$quoteme on` to opt back in.")
            else:
                await ctx.send("You are currently **opted in** to being quoted. Use `$quoteme off` to opt out.")
            return

        toggle = toggle.lower()
        if toggle == "off":
            await db.quote_optout(ctx.author.id)
            await ctx.send("You have opted out of being quoted. Others can no longer quote your messages.")
        elif toggle == "on":
            success = await db.quote_optin(ctx.author.id)
            if success:
                await ctx.send("You have opted back in. Others can quote your messages again.")
            else:
                await ctx.send("You were already opted in.")
        else:
            await ctx.send("Usage: `$quoteme [on|off]`")


async def setup(bot):
    await bot.add_cog(QuoteGenerator(bot))
    from cogs.quote_generator_cog.admin import QuoteAdminCog
    await bot.add_cog(QuoteAdminCog(bot))
