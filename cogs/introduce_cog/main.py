"""Introduce cog — slash and prefix commands for introductions and exchange partner requests."""
import logging
from datetime import timedelta

import discord
from discord import ButtonStyle, Embed, Interaction, app_commands
from discord.ext import commands
from discord.ui import Button, View, button

from base_cog import BaseCog
from cogs.utils.embeds import green_embed, red_embed

from .config import (
    COMMAND_CHANNEL_ID,
    INTRODUCTIONS_CHANNEL_ID,
    REPOST_COOLDOWN_DAYS,
    REPOST_GRACE_MINUTES,
    detect_ui_lang,
)
from .i18n import t
from .modals import _audit_log, _build_exchange_embed
from .views import IntroStartView

logger = logging.getLogger(__name__)


def _intro_embed(lang: str) -> Embed:
    """Build the intro start embed."""
    embed = Embed(
        title=t("intro_title", lang),
        description=t("intro_description", lang),
        color=discord.Color.blue(),
    )
    embed.set_footer(text=t("intro_footer", lang))
    return embed


async def _start_intro_flow(interaction: Interaction) -> None:
    """Send the ephemeral intro start view."""
    lang = detect_ui_lang(interaction.user) if isinstance(interaction.user, discord.Member) else "en"

    # Block if they already have an active exchange post
    existing = await interaction.client.db.get_exchange_post(interaction.user.id)
    if existing:
        await interaction.response.send_message(
            embed=red_embed(t("error_already_posted", lang)), ephemeral=True,
        )
        return

    view = IntroStartView(introductions_channel_id=INTRODUCTIONS_CHANNEL_ID, lang=lang)
    await interaction.response.send_message(embed=_intro_embed(lang), view=view, ephemeral=True)
    logger.info("Introduction started by user %s", interaction.user.id)


class IntroduceButton(View):
    """Persistent button that kicks off the introduction flow."""

    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Introduce Yourself", style=ButtonStyle.primary, custom_id="introduce:start", emoji="👋")
    async def start_button(self, interaction: Interaction, btn: Button):
        await _start_intro_flow(interaction)


class IntroduceCog(BaseCog):
    """Introduce yourself and find language exchange partners."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        bot.add_view(IntroduceButton())

    # ── /introduce ──

    @app_commands.command(name="introduce", description="Introduce yourself to the community")
    async def introduce_slash(self, interaction: Interaction):
        if interaction.channel_id != COMMAND_CHANNEL_ID:
            ch = interaction.client.get_channel(COMMAND_CHANNEL_ID)
            mention = ch.mention if ch else f"<#{COMMAND_CHANNEL_ID}>"
            await interaction.response.send_message(f"Use this in {mention}.", ephemeral=True)
            return
        await _start_intro_flow(interaction)

    # ── $introduce (prefix — posts persistent button) ──

    @commands.command(name="introduce")
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def introduce_prefix(self, ctx: commands.Context):
        if ctx.channel.id != COMMAND_CHANNEL_ID:
            ch = ctx.bot.get_channel(COMMAND_CHANNEL_ID)
            mention = ch.mention if ch else f"<#{COMMAND_CHANNEL_ID}>"
            await ctx.send(f"Use this in {mention}.")
            return
        embed = Embed(
            title="👋 Introduce Yourself",
            description="Click the button below to introduce yourself to the community!",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed, view=IntroduceButton())

    # ── /exchange (manage your exchange post) ──

    exchange_group = app_commands.Group(name="exchange", description="Manage your exchange partner post")

    @exchange_group.command(name="delete", description="Delete your exchange partner post")
    async def exchange_delete(self, interaction: Interaction):
        post = await interaction.client.db.get_exchange_post(interaction.user.id)
        if not post:
            await interaction.response.send_message(
                embed=red_embed("You don't have an active exchange post."), ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        channel = interaction.client.get_channel(post["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(post["message_id"])
                await msg.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                logger.warning("Failed to delete exchange message %s", post["message_id"])

        await interaction.client.db.delete_exchange_post(interaction.user.id)
        await interaction.followup.send(embed=green_embed("Your exchange post has been deleted."), ephemeral=True)
        await _audit_log(interaction.client, interaction.user, "Exchange deleted (self)")

    @exchange_group.command(name="repost", description="Repost your exchange partner request")
    async def exchange_repost(self, interaction: Interaction):
        post = await interaction.client.db.get_exchange_post(interaction.user.id)
        if not post:
            await interaction.response.send_message(
                embed=red_embed("You don't have an active exchange post. Use `/introduce` to create one."),
                ephemeral=True,
            )
            return

        can_repost, posted_at = await interaction.client.db.can_repost_exchange(
            interaction.user.id, REPOST_COOLDOWN_DAYS, REPOST_GRACE_MINUTES,
        )
        if not can_repost:
            next_date = posted_at + timedelta(days=REPOST_COOLDOWN_DAYS)
            await interaction.response.send_message(
                embed=red_embed(
                    f"You can repost after <t:{int(next_date.timestamp())}:R>.\n\n"
                    f"-# Reposts are allowed within {REPOST_GRACE_MINUTES} minutes of posting, "
                    f"or after {REPOST_COOLDOWN_DAYS} days."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Fetch the user as a member for role-based color
        guild = interaction.guild
        member = guild.get_member(interaction.user.id) if guild else interaction.user

        # Delete old message
        channel = interaction.client.get_channel(post["channel_id"])
        if channel:
            try:
                old_msg = await channel.fetch_message(post["message_id"])
                await old_msg.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                logger.warning("Failed to delete old exchange post %s", post["message_id"])

        # Rebuild from stored data
        post_data = post.get("post_data")
        if not post_data:
            await interaction.client.db.delete_exchange_post(interaction.user.id)
            await interaction.followup.send(
                embed=red_embed("Your post data could not be found. Use `/introduce` to create a new one."),
                ephemeral=True,
            )
            return

        view = _build_exchange_embed(post_data, member)

        # Post in the introductions channel
        target_channel = interaction.client.get_channel(INTRODUCTIONS_CHANNEL_ID)
        if not target_channel:
            await interaction.followup.send(embed=red_embed("Introductions channel not found."), ephemeral=True)
            return

        try:
            new_msg = await target_channel.send(embed=view)
        except discord.HTTPException:
            logger.exception("Failed to repost exchange layout")
            await interaction.followup.send(embed=red_embed("Failed to repost. Please try again later."), ephemeral=True)
            return

        await interaction.client.db.save_exchange_post(interaction.user.id, new_msg.id, target_channel.id, post_data=post_data)
        await interaction.followup.send(embed=green_embed("Your exchange post has been reposted!"), ephemeral=True)
        await _audit_log(interaction.client, interaction.user, "Exchange reposted")

    # ── Admin: delete someone else's exchange post ──

    @exchange_group.command(name="remove", description="[Mod] Remove someone's exchange post")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(user="The user whose post to remove")
    async def exchange_remove(self, interaction: Interaction, user: discord.Member):
        post = await interaction.client.db.get_exchange_post(user.id)
        if not post:
            await interaction.response.send_message(
                embed=red_embed(f"{user.mention} doesn't have an active exchange post."), ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        channel = interaction.client.get_channel(post["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(post["message_id"])
                await msg.delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                logger.warning("Failed to delete exchange message %s for user %s", post["message_id"], user.id)

        await interaction.client.db.delete_exchange_post(user.id)
        await interaction.followup.send(
            embed=green_embed(f"Removed {user.mention}'s exchange post."), ephemeral=True,
        )
        await _audit_log(interaction.client, interaction.user, f"Exchange removed (mod) — target: {user} (`{user.id}`)")

    # ── Admin: reset a user's exchange post record ──

    @commands.command(name="exchangereset")
    @commands.has_permissions(manage_messages=True)
    async def exchange_reset(self, ctx: commands.Context, user: discord.Member):
        """Reset a user's exchange post DB entry so they can post again."""
        deleted = await ctx.bot.db.delete_exchange_post(user.id)
        if deleted:
            await ctx.send(f"✅ Reset exchange post for {user.mention} (`{user.id}`).")
            await _audit_log(ctx.bot, ctx.author, f"Exchange reset (mod) — target: {user} (`{user.id}`)")
        else:
            await ctx.send(f"{user.mention} has no exchange post to reset.")


async def setup(bot: commands.Bot):
    await bot.add_cog(IntroduceCog(bot))
    logger.info("IntroduceCog loaded")
