"""General cog — help, info, ping, and invite commands."""
import logging
import time

import discord
from discord import Color, Embed, Interaction, app_commands
from discord.ext import commands
from discord.ext.commands import Bot, command

from base_cog import BaseCog
from cogs.general_cog.config import BOT_AUTHOR_ID, DPY, INVITE_LINK, REPO
from cogs.utils.embeds import green_embed

logger = logging.getLogger(__name__)

# Cogs hidden from the public /help overview (owner/admin-only)
HIDDEN_COGS = {"AdminCog", "General", "DatabaseCommands", "RelayCog", "AskCog"}


def _is_owner_command(cmd: commands.Command) -> bool:
    """Check if a prefix command has an is_owner check."""
    return any(
        getattr(check, "__qualname__", "").startswith("is_owner")
        for check in cmd.checks
    )


def _format_prefix_cmd(prefix: str, cmd: commands.Command) -> str:
    """Format a single prefix command for embed display."""
    name = f"`{prefix}{cmd.qualified_name}`"
    doc = cmd.short_doc or cmd.description or ""
    return f"{name} — {doc}" if doc else name


def _format_slash_cmd(cmd: app_commands.Command | app_commands.Group) -> str:
    """Format a single slash command/group for embed display."""
    if isinstance(cmd, app_commands.Group):
        return f"`/{cmd.qualified_name}` — {cmd.description}"
    desc = cmd.description or ""
    return f"`/{cmd.qualified_name}` — {desc}" if desc else f"`/{cmd.qualified_name}`"


def _build_cog_field(
    cog_name: str,
    cog_desc: str,
    slash_lines: list[str],
    prefix_lines: list[str],
) -> tuple[str, str]:
    """Return (field_name, field_value) for a cog's help section."""
    lines = slash_lines + prefix_lines
    value = "\n".join(lines) if lines else "*No commands*"
    return cog_name, value


def _collect_cog_entries(bot: Bot) -> list[tuple[str, str, list[str], list[str]]]:
    """Collect (cog_name, cog_desc, slash_lines, prefix_lines) for visible cogs."""
    entries: list[tuple[str, str, list[str], list[str]]] = []
    prefix = bot.command_prefix

    for name, cog in sorted(bot.cogs.items()):
        if name in HIDDEN_COGS:
            continue

        slash_lines: list[str] = []
        for cmd in cog.walk_app_commands():
            if isinstance(cmd, app_commands.Command):
                slash_lines.append(_format_slash_cmd(cmd))

        # Also show top-level groups themselves
        for cmd in cog.get_app_commands():
            if isinstance(cmd, app_commands.Group):
                slash_lines.insert(0, _format_slash_cmd(cmd))

        prefix_lines: list[str] = []
        for cmd in cog.get_commands():
            if _is_owner_command(cmd):
                continue
            prefix_lines.append(_format_prefix_cmd(prefix, cmd))

        if slash_lines or prefix_lines:
            entries.append((name, cog.description or "", slash_lines, prefix_lines))

    return entries


class General(BaseCog):
    """General bot commands — help, info, ping."""

    def __init__(self, bot: Bot):
        super().__init__(bot)

    # ------------------------------------------------------------------
    # /help  (slash)
    # ------------------------------------------------------------------

    @app_commands.command(
        name="help",
        description="View all available bot commands and features",
    )
    @app_commands.describe(category="Choose a specific cog to view")
    async def help_slash(self, interaction: Interaction, category: str | None = None):
        """Auto-generated help from cog docstrings and command metadata."""
        entries = _collect_cog_entries(self.bot)

        if category:
            # Find matching cog (case-insensitive)
            match = next(
                (e for e in entries if e[0].lower() == category.lower()),
                None,
            )
            if not match:
                await interaction.response.send_message(
                    f"Unknown category `{category}`. Use `/help` to see all.",
                    ephemeral=True,
                )
                return

            cog_name, cog_desc, slash_lines, prefix_lines = match
            embed = Embed(
                title=f"📖 {cog_name}",
                description=cog_desc or None,
                color=Color.green(),
            )
            if slash_lines:
                embed.add_field(
                    name="Slash Commands",
                    value="\n".join(slash_lines),
                    inline=False,
                )
            if prefix_lines:
                embed.add_field(
                    name="Prefix Commands",
                    value="\n".join(prefix_lines),
                    inline=False,
                )
        else:
            embed = Embed(
                title="🤖 Hablemos Bot — Command Guide",
                description=(
                    "A language learning bot for Spanish and English learners!\n"
                    "Use `/help <category>` for details on a specific category."
                ),
                color=Color.blue(),
            )
            for cog_name, cog_desc, slash_lines, prefix_lines in entries:
                field_name, field_value = _build_cog_field(
                    cog_name, cog_desc, slash_lines, prefix_lines,
                )
                # Truncate to embed field limit
                if len(field_value) > 1024:
                    field_value = field_value[:1021] + "…"
                embed.add_field(name=field_name, value=field_value, inline=False)

            embed.set_footer(text="Use /help <category> for detailed information")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @help_slash.autocomplete("category")
    async def _help_category_autocomplete(
        self, interaction: Interaction, current: str,
    ) -> list[app_commands.Choice[str]]:
        entries = _collect_cog_entries(self.bot)
        return [
            app_commands.Choice(name=name, value=name)
            for name, *_ in entries
            if current.lower() in name.lower()
        ][:25]

    # ------------------------------------------------------------------
    # $help  (prefix) — keeps the existing fallback-to-command.help pattern
    # ------------------------------------------------------------------

    @command()
    async def help(self, ctx, arg=''):
        if arg:
            requested = self.bot.get_command(arg)
            if not requested:
                await ctx.send("I was unable to find the command you requested")
                return
            message = f"**{self.bot.command_prefix}{requested.qualified_name}**\n"
            if requested.aliases:
                message += f"Aliases: `{'`, `'.join(requested.aliases)}`\n"
            if requested.help:
                message += requested.help
            await ctx.send(embed=green_embed(message))
        else:
            to_send = (
                f"Type `{self.bot.command_prefix}help <command>` for more info "
                f"on any command.\nUse `/help` for the full command guide."
            )
            await ctx.send(embed=green_embed(to_send))

    # ------------------------------------------------------------------
    # Utility commands
    # ------------------------------------------------------------------

    @command()
    async def info(self, ctx):
        """Information about the bot."""
        text = (
            f"The bot was coded in Python using the [discord.py]({DPY}) framework.\n\n"
            f"To report an error or make a suggestion please message "
            f"<@{BOT_AUTHOR_ID}>\n[Github Repository]({REPO})"
        )
        await ctx.send(embed=green_embed(text))

    @command()
    async def invite(self, ctx):
        """Bot invitation link."""
        text = f"[Invite the bot to your server]({INVITE_LINK})"
        await ctx.send(embed=green_embed(text))

    @command()
    async def ping(self, ctx):
        """Check bot latency: WebSocket, API round-trip, and database."""
        ws = round(self.bot.latency * 1000, 2)

        start = time.perf_counter()
        msg = await ctx.send(embed=green_embed("Pinging..."))
        api = round((time.perf_counter() - start) * 1000, 2)

        start = time.perf_counter()
        await self.bot.db._fetchval("SELECT 1")
        db = round((time.perf_counter() - start) * 1000, 2)

        embed = Embed(title="🏓 Pong!", color=Color.blurple())
        embed.add_field(name="WebSocket", value=f"`{ws}ms`", inline=True)
        embed.add_field(name="API", value=f"`{api}ms`", inline=True)
        embed.add_field(name="Database", value=f"`{db}ms`", inline=True)
        await msg.edit(embed=embed)

    @command()
    @commands.is_owner()
    async def permdebug(self, ctx, channel: discord.abc.GuildChannel | None = None):
        """Dump computed permissions for the bot in a channel.

        Usage:
          $permdebug                  — current channel
          $permdebug #some-channel    — specific channel
          $permdebug 123456789012345  — channel by ID

        Falls back to DM if the bot can't send in the target channel.
        """
        if ctx.guild is None:
            await ctx.send("Must be run in a guild.")
            return

        target = channel or ctx.channel
        me = ctx.guild.me
        perms = target.permissions_for(me)

        roles = ", ".join(f"{r.name}({r.id})" for r in me.roles)

        # Per-channel + category-level role overwrites that apply to the bot
        overwrites: list[str] = []
        for role in me.roles:
            ow = target.overwrites_for(role)
            pair = ow.pair()  # (allow, deny) Permissions objects
            allow = [name for name, val in pair[0] if val]
            deny = [name for name, val in pair[1] if val]
            if allow or deny:
                overwrites.append(
                    f"role `{role.name}`: allow={allow or '—'} deny={deny or '—'}"
                )

        member_ow = target.overwrites_for(me)
        mpair = member_ow.pair()
        m_allow = [name for name, val in mpair[0] if val]
        m_deny = [name for name, val in mpair[1] if val]
        if m_allow or m_deny:
            overwrites.append(
                f"member override: allow={m_allow or '—'} deny={m_deny or '—'}"
            )

        parent = getattr(target, "category", None)
        parent_info = (
            f"{parent.name} ({parent.id})" if parent else "— (no category)"
        )

        lines = [
            f"**permdebug** for `#{target.name}`",
            f"channel_id: `{target.id}`",
            f"channel_type: `{type(target).__name__}`",
            f"category: `{parent_info}`",
            f"bot_roles: {roles or '—'}",
            "",
            "**Computed perms (what the bot actually has here):**",
            f"  view_channel:              {perms.view_channel}",
            f"  read_message_history:      {perms.read_message_history}",
            f"  send_messages:             {perms.send_messages}",
            f"  send_messages_in_threads:  {perms.send_messages_in_threads}",
            f"  embed_links:               {perms.embed_links}",
            f"  attach_files:              {perms.attach_files}",
            f"  add_reactions:             {perms.add_reactions}",
            f"  manage_messages:           {perms.manage_messages}",
            f"  administrator:             {perms.administrator}",
            "",
            "**Channel/category overwrites touching bot roles:**",
        ]
        if overwrites:
            lines.extend(f"  {line}" for line in overwrites)
        else:
            lines.append("  (none)")
        report = "\n".join(lines)

        # Always log so Railway captures it even if all sends fail
        logger.info("permdebug for channel %s (%s):\n%s", target.name, target.id, report)

        # Try channel first, fall back to DM
        try:
            await ctx.send(f"```\n{report[:1900]}\n```")
            return
        except discord.Forbidden:
            pass

        try:
            await ctx.author.send(f"```\n{report[:1900]}\n```")
        except discord.Forbidden:
            logger.warning("permdebug: couldn't send in channel or DM; see server log above")


async def setup(bot):
    await bot.add_cog(General(bot))
