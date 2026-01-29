from cogs.quote_generator_cog.quote_generator_helper.image_creator import dir_path, create_image
from cogs.quote_generator_cog.quote_generator_helper.image_creator2 import dir_path as dir_path2, create_image2
from base_cog import BaseCog

from re import sub
from os import remove
import logging

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

    logger.info(f"Final username: {username!r}")
    return username


async def get_html_css_info(channel, message_id, server):
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

    @command(aliases=['q', ])
    @cooldown(1, 10, type=BucketType.user)
    async def quote(self, ctx, *user_input):
        """
        (still testing, please report any errors or suggestions)
        Creates a quote using a **message url**, **your own message** or **replying to a message**.
        Images and custom emojis won't show up and there's a limit to 150 words.

        Example usage:
        `$quote https://discord.com/channels/731403448502845501/808679873837137940/916938526329798718`
        (creates a quote using a specific message)
        `$quote todo es bronca y dolor`
        (creates a quote using your own message)
        """

        is_message_reply = ctx.message.reference is not None
        if len(user_input) == 0 and not is_message_reply:
            return await ctx.send("Please type `$help quote` for info on correct usage")

        if len(user_input) == 1 and len(user_input[0]) == 18 and user_input[0].isdigit() and not is_message_reply:
            return await ctx.send(
                "You tried to use a message_id. Please use a link or just a regular message. See `$help quote` for "
                "correct usage")

        if is_message_reply:
            message_id = ctx.message.reference.message_id
            guild_id = ctx.message.reference.guild_id
            channel_id = ctx.message.reference.channel_id
            server = self.bot.get_guild(guild_id)
            server = self.bot.get_guild(guild_id)
            if server is None:
                # Handle the error, e.g. by logging a message or raising an exception
                print(f"Could not find server with ID {guild_id}")
            else:
                channel = server.get_channel(channel_id)
                # Continue with your code...

            user_nick, user_avatar, message_content = await get_html_css_info(channel, message_id, server)

        elif len(user_input) == 1 and user_input[0].startswith("https://discord.com/channels/"):
            link = user_input[0].split('/')
            server_id = int(link[4])
            channel_id = int(link[5])
            msg_id = int(link[6])

            server = self.bot.get_guild(server_id)
            if server is None:
                return await ctx.send("I can't access this server")
            channel = server.get_channel(channel_id)
            if channel is None:
                return await ctx.send("I can't access this channel")

            user_nick, user_avatar, message_content = await get_html_css_info(channel, msg_id, server)

        else:
            message_content = remove_emoji_from_message(' '.join(user_input))
            # Convert any mention markup present in the invoking command message itself.
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

        if len(message_content) > 250:
            return await ctx.send("Beep boop, I can't create an image. I'm limited to 150 characters")
        generated_url = create_image(user_nick, user_avatar, message_content)

        await ctx.send(file=File(generated_url))

        # delete file
        remove(f"{dir_path}/picture.png")

    @command(aliases=['q2', ])
    @cooldown(1, 10, type=BucketType.user)
    async def quote2(self, ctx, *user_input):
        """
        Creates a quote using the new card style. Usage mirrors `$quote`.
        """

        is_message_reply = ctx.message.reference is not None
        if len(user_input) == 0 and not is_message_reply:
            return await ctx.send("Please type `$help quote2` for info on correct usage")

        if len(user_input) == 1 and len(user_input[0]) == 18 and user_input[0].isdigit() and not is_message_reply:
            return await ctx.send(
                "You tried to use a message_id. Please use a link or just a regular message. See `$help quote2` for correct usage")

        if is_message_reply:
            message_id = ctx.message.reference.message_id
            guild_id = ctx.message.reference.guild_id
            channel_id = ctx.message.reference.channel_id
            server = self.bot.get_guild(guild_id)
            server = self.bot.get_guild(guild_id)
            if server is None:
                print(f"Could not find server with ID {guild_id}")
            else:
                channel = server.get_channel(channel_id)

            user_nick, user_avatar, message_content = await get_html_css_info(channel, message_id, server)

        elif len(user_input) == 1 and user_input[0].startswith("https://discord.com/channels/"):
            link = user_input[0].split('/')
            server_id = int(link[4])
            channel_id = int(link[5])
            msg_id = int(link[6])

            server = self.bot.get_guild(server_id)
            if server is None:
                return await ctx.send("I can't access this server")
            channel = server.get_channel(channel_id)
            if channel is None:
                return await ctx.send("I can't access this channel")

            user_nick, user_avatar, message_content = await get_html_css_info(channel, msg_id, server)

        else:
            message_content = remove_emoji_from_message(' '.join(user_input))
            # Convert any mention markup present in the invoking command message itself.
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

        if len(message_content) > 250:
            return await ctx.send("Beep boop, I can't create an image. I'm limited to 150 characters")

        generated_url = create_image2(user_nick, user_avatar, message_content)

        await ctx.send(file=File(generated_url))

        # delete file
        remove(f"{dir_path2}/picture2.png")


async def setup(bot):
    await bot.add_cog(QuoteGenerator(bot))
