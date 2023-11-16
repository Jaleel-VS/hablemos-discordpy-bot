from cogs.quote_generator_cog.quote_generator_helper.image_creator import dir_path, create_image
from base_cog import BaseCog

from re import sub
from os import remove

from discord.ext.commands import command, cooldown, BucketType
from discord import File
import demoji


def get_img_url(url_identifier: str):
    if url_identifier is None:  # user doesn't have a profile picture
        return "https://i.imgur.com/z9tOsSz.png"
    return str(url_identifier)[:-4] + '256'


def remove_emoji_from_message(message):  # for custom emojis
    return sub("<:[A-Za-z0-9_]+:([0-9]+)>", '', message).replace("  ", " ")


def give_emoji_free_text(text: str) -> str:  # for standard emojis
    return demoji.replace(text, '')[:28]


async def get_html_css_info(channel, message_id, server):
    message = await channel.fetch_message(message_id)
    user = message.author
    user_id = message.author.id
    message_content = remove_emoji_from_message(message.content)

    if server.get_member(user_id) is None:
        user_nick = user.name
    else:
        user_nick = user.display_name if user.nick is None else give_emoji_free_text(user.nick)

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
            user_nick = ctx.author.display_name if ctx.author.nick is None else give_emoji_free_text(ctx.author.nick)
            user_avatar = get_img_url(ctx.author.avatar)

        if len(message_content) > 150:
            return await ctx.send("Beep boop, I can't create an image. I'm limited to 150 characters")
        generated_url = create_image(user_nick, user_avatar, message_content)

        await ctx.send(file=File(generated_url))

        # delete file
        remove(f"{dir_path}/quote_generator_helper/picture.png")


async def setup(bot):
    await bot.add_cog(QuoteGenerator(bot))
