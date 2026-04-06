"""Interactions cog — tracks reply/mention interactions and provides analysis commands."""
import logging
from datetime import UTC, datetime

import discord
from discord import Color, ui
from discord.ext import commands, tasks

from base_cog import BaseCog
from cogs.utils.duration import format_duration, parse_duration
from cogs.utils.plural import plural
from cogs.utils.visibility import VisibilityView

logger = logging.getLogger(__name__)

INTERACTIONS_RETENTION_DAYS = 90


class InteractionsCog(BaseCog):
    """Track and analyze reply/mention interactions between users."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self._interaction_errors = 0
        self._last_interactions_msg: discord.Message | None = None
        self.daily_purge.start()

    async def cog_unload(self):
        self.daily_purge.cancel()

    # ── Recording ──

    async def _record(self, channel_id: int, guild_id: int, author_id: int, target_id: int, kind: str) -> None:
        """Record an interaction, suppressing repeated DB errors to avoid log spam."""
        try:
            await self.bot.db.record_interaction(channel_id, guild_id, author_id, target_id, kind)
            self._interaction_errors = 0
        except Exception:
            self._interaction_errors += 1
            if self._interaction_errors <= 3:
                logger.exception("Failed to record %s interaction", kind)
            elif self._interaction_errors == 4:
                logger.error("Suppressing further interaction recording errors")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track reply and mention interactions to the database."""
        if message.author.bot or not message.guild:
            return

        author_id = message.author.id
        channel_id = message.channel.id
        guild_id = message.guild.id

        # Track replies
        replied_to_id = None
        ref = message.reference
        if ref and ref.resolved and not isinstance(ref.resolved, discord.DeletedReferencedMessage):
            target = ref.resolved.author
            if not target.bot and target.id != author_id:
                replied_to_id = target.id
                await self._record(channel_id, guild_id, author_id, target.id, "reply")

        # Track mentions (skip the reply target — Discord auto-mentions them)
        for mentioned in message.mentions:
            if not mentioned.bot and mentioned.id != author_id and mentioned.id != replied_to_id:
                await self._record(channel_id, guild_id, author_id, mentioned.id, "mention")

    # ── Daily purge ──

    @tasks.loop(hours=24)
    async def daily_purge(self):
        """Purge old interaction rows."""
        try:
            purged = await self.bot.db.purge_old_interactions(INTERACTIONS_RETENTION_DAYS)
            logger.info("Interactions purge: %s rows deleted", purged)
        except Exception:
            logger.exception("Interactions purge failed")

    @daily_purge.before_loop
    async def before_daily_purge(self):
        await self.bot.wait_until_ready()

    # ── $interactions (top pairs) ──

    @commands.command(name='interactions')
    @commands.cooldown(1, 60, commands.BucketType.default)
    async def interactions(self, ctx: commands.Context, duration: str = "7d", channel: discord.TextChannel = None):
        """
        Show top reply/mention pairs in a channel (from tracked data).

        Usage: $interactions [duration] [#channel]
        Examples: $interactions 12h | $interactions 3d #general | $interactions 1d12h
        """
        channel = channel or ctx.channel

        try:
            td = parse_duration(duration)
        except ValueError as exc:
            await ctx.send(str(exc))
            return

        after = datetime.now(UTC) - td
        duration_label = format_duration(td)

        top_pairs = await self.bot.db.get_top_pairs(channel.id, after)
        stats = await self.bot.db.get_interaction_stats(channel.id, after)

        if not top_pairs:
            await ctx.send(f"No interactions recorded in #{channel.name} over the last {duration_label}.")
            return

        guild = ctx.guild

        def _display_name(uid: int) -> str:
            member = guild.get_member(uid) if guild else None
            if member:
                return member.nick or member.global_name or member.name
            return f"User {uid}"

        MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

        lines = []
        for i, pair in enumerate(top_pairs, 1):
            name_a = _display_name(pair['user_a'])
            name_b = _display_name(pair['user_b'])
            parts = []
            if pair['replies']:
                parts.append(f"{plural(pair['replies']):reply/replies}")
            if pair['mentions']:
                parts.append(f"{plural(pair['mentions']):mention}")
            detail = ", ".join(parts)
            rank = MEDALS.get(i, f"**{i}.**")
            lines.append(f"{rank} {name_a}  &  {name_b}\n-# {detail}")

        view = ui.LayoutView()
        view.add_item(ui.Container(
            ui.TextDisplay(f"## Interactions in #{channel.name}\n-# Top pairs by replies & mentions"),
            ui.Separator(visible=True),
            ui.TextDisplay("\n".join(lines)),
            ui.Separator(visible=True),
            ui.TextDisplay(
                f"**{stats['unique_pairs']}** unique pairs — "
                f"**{stats['total_replies']}** replies, "
                f"**{stats['total_mentions']}** mentions\n"
                f"-# Last {duration_label}"
            ),
            accent_colour=Color.blurple(),
        ))
        await ctx.send(view=view)
        self._last_interactions_msg = ctx.message

    @interactions.error
    async def interactions_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Show cooldown with a jump link to the last invocation."""
        if isinstance(error, commands.CommandOnCooldown):
            msg = f"⏱️ On cooldown — try again in {round(error.retry_after)}s."
            if self._last_interactions_msg:
                msg += f" [Last used here]({self._last_interactions_msg.jump_url})"
            await ctx.send(msg)
            return
        raise error

    # ── $whotalks / $wt (per-user) ──

    def _build_wt_view(self, display_name: str, scope: str, duration_label: str,
                       partners: list, guild: discord.Guild | None) -> ui.LayoutView:
        """Build the LayoutView for whotalks results."""
        MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, row in enumerate(partners, 1):
            member = guild.get_member(row['partner_id']) if guild else None
            name = member.nick or member.global_name or member.name if member else f"User {row['partner_id']}"
            parts = []
            if row['replies']:
                parts.append(f"{plural(row['replies']):reply/replies}")
            if row['mentions']:
                parts.append(f"{plural(row['mentions']):mention}")
            detail = ", ".join(parts)
            rank = MEDALS.get(i, f"**{i}.**")
            lines.append(f"{rank} {name}\n-# {detail}")

        total = sum(r['score'] for r in partners)

        view = ui.LayoutView()
        view.add_item(ui.Container(
            ui.TextDisplay(f"## Who does {display_name} talk to?\n-# Top partners by replies & mentions ({scope})"),
            ui.Separator(visible=True),
            ui.TextDisplay("\n".join(lines)),
            ui.Separator(visible=True),
            ui.TextDisplay(
                f"**{len(partners)}** unique partners — "
                f"**{total}** weighted interactions\n"
                f"-# Last {duration_label}"
            ),
            accent_colour=Color.blurple(),
        ))
        return view

    @commands.command(name="whotalks", aliases=["wt"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def whotalks(
        self,
        ctx: commands.Context,
        user: discord.Member = None,
        duration: str = "30d",
        channel: discord.TextChannel = None,
    ):
        """Show who you interact with the most.

        Usage: $wt [duration] [#channel]
        Examples: $wt | $wt 7d | $wt 30d #general
        """
        if user is not None and user.id != ctx.author.id:
            await ctx.send("🔒 You can only view your own interaction stats.")
            return

        user = ctx.author
        try:
            td = parse_duration(duration)
        except ValueError as exc:
            await ctx.send(str(exc))
            return

        after = datetime.now(UTC) - td
        duration_label = format_duration(td)

        partners = await self.bot.db.get_top_partners_for_user(
            user.id, after, guild_id=ctx.guild.id,
            channel_id=channel.id if channel else None,
        )

        scope = f"in #{channel.name}" if channel else "server-wide"
        if not partners:
            await ctx.send(f"No interactions recorded for {user.display_name} {scope} over the last {duration_label}.")
            return

        result_view = self._build_wt_view(user.display_name, scope, duration_label, partners, ctx.guild)

        async def on_public(cmd_msg):
            kwargs = {'view': result_view, 'mention_author': False}
            if cmd_msg:
                await cmd_msg.reply(**kwargs)
            else:
                kwargs.pop('mention_author', None)
                await ctx.channel.send(**kwargs)

        async def on_private(interaction):
            await interaction.response.send_message(view=result_view, ephemeral=True)

        visibility = VisibilityView(
            author_id=ctx.author.id,
            command_message=ctx.message,
            on_public=on_public,
            on_private=on_private,
        )
        prompt = await ctx.send("Ready. Send publicly or privately?", view=visibility)
        visibility.prompt_message = prompt


async def setup(bot: commands.Bot):
    await bot.add_cog(InteractionsCog(bot))
