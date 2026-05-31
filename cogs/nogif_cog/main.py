"""No-GIF cog — temporarily block a user from sending GIFs/embeds.

Commands (mod-only):
  $nogif @user <duration>   — apply the restriction (e.g. 10m, 2h, 1d)
  $ungif @user              — lift it early

How it works
------------
The bot creates (once per guild) a "Sin GIFs" role and sets a channel
permission overwrite of ``embed_links=False`` on every text channel.
Assigning that role to a user denies their embed links even if another
role grants them server-wide — because channel overwrites take priority.

Restrictions persist across bot restarts via the ``nogif_restrictions``
DB table; pending timers are rescheduled in ``cog_load``.
"""

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import green_embed, red_embed, yellow_embed

from .config import NOGIF_MAX_SECONDS, NOGIF_ROLE_NAME, SETTING_KEY_PREFIX

logger = logging.getLogger(__name__)

# ── Duration parser ───────────────────────────────────────────────────────────

_DURATION_RE = re.compile(r"^(\d+)([smhd])$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_UNIT_LABELS = {"s": "segundo(s)", "m": "minuto(s)", "h": "hora(s)", "d": "día(s)"}


def _parse_duration(value: str) -> tuple[int, str]:
    """Parse '10m', '2h', '1d', '30s' → (total_seconds, human_label).

    Raises ValueError for unrecognised formats.
    """
    m = _DURATION_RE.match(value.strip())
    if not m:
        raise ValueError(value)
    amount, unit = int(m.group(1)), m.group(2).lower()
    return amount * _UNIT_SECONDS[unit], f"{amount} {_UNIT_LABELS[unit]}"


# ── Cog ───────────────────────────────────────────────────────────────────────

class NoGif(BaseCog):
    """Temporarily restrict a member from sending GIFs/embeds."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        # user_id → asyncio.Task (scheduled lift)
        self._tasks: dict[int, asyncio.Task] = {}

    async def cog_load(self) -> None:
        """Schedule removal tasks for any restrictions that survived a restart."""
        self._restore_task = asyncio.create_task(
            self._restore_pending(), name="nogif-restore"
        )

    async def cog_unload(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()

    # ── Role / overwrite helpers ──────────────────────────────────────────────

    async def _get_or_create_role(self, guild: discord.Guild) -> discord.Role:
        """Return the Sin GIFs role, creating it (and its overwrites) if needed."""
        setting_key = f"{SETTING_KEY_PREFIX}.{guild.id}"
        stored_id = await self.bot.db.get_bot_setting(setting_key)

        if stored_id:
            role = guild.get_role(int(stored_id))
            if role is not None:
                return role
            # Role was deleted — fall through to recreate it.

        role = await guild.create_role(
            name=NOGIF_ROLE_NAME,
            reason="Auto-created by bot for nogif restrictions",
            mentionable=False,
            hoist=False,
        )
        await self.bot.db.set_bot_setting(setting_key, role.id)
        logger.info("Created '%s' role (id=%s) in guild %s", NOGIF_ROLE_NAME, role.id, guild.id)

        await self._apply_overwrites(guild, role)
        return role

    async def _apply_overwrites(
        self, guild: discord.Guild, role: discord.Role
    ) -> None:
        """Set embed_links=False overwrite for role on every text channel."""
        overwrite = discord.PermissionOverwrite(embed_links=False)
        failed = 0
        for channel in guild.text_channels:
            try:
                await channel.set_permissions(
                    role,
                    overwrite=overwrite,
                    reason="nogif: deny embed_links for Sin GIFs role",
                )
            except discord.Forbidden:
                failed += 1
                logger.warning(
                    "No permission to set overwrite on #%s in guild %s",
                    channel.name, guild.id,
                )
            except discord.HTTPException as exc:
                failed += 1
                logger.warning(
                    "HTTP error setting overwrite on #%s: %s", channel.name, exc,
                )
        if failed:
            logger.warning(
                "Overwrites skipped on %d channel(s) in guild %s", failed, guild.id,
            )

    # ── Restriction lifecycle ─────────────────────────────────────────────────

    async def _apply_restriction(
        self,
        member: discord.Member,
        role: discord.Role,
        seconds: int,
        label: str,
    ) -> None:
        """Assign the role, persist to DB, and schedule automatic removal."""
        await member.add_roles(role, reason=f"nogif: {label}")

        expires_at = datetime.now(UTC) + timedelta(seconds=seconds)
        await self.bot.db.upsert_nogif_restriction(member.id, member.guild.id, expires_at)

        # Cancel any existing timer for this user.
        existing = self._tasks.pop(member.id, None)
        if existing:
            existing.cancel()

        task = asyncio.create_task(
            self._scheduled_lift(member, role, seconds),
            name=f"nogif-lift-{member.id}",
        )
        self._tasks[member.id] = task

    async def _lift_restriction(
        self, member: discord.Member, role: discord.Role, *, reason: str = "nogif expired"
    ) -> None:
        """Remove the role and clean up DB + task registry."""
        try:
            await member.remove_roles(role, reason=reason)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound) as exc:
            logger.warning(
                "Could not remove '%s' from %s (%s): %s",
                NOGIF_ROLE_NAME, member, member.id, exc,
            )
        await self.bot.db.delete_nogif_restriction(member.id, member.guild.id)
        self._tasks.pop(member.id, None)

    async def _scheduled_lift(
        self, member: discord.Member, role: discord.Role, seconds: int
    ) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        await self._lift_restriction(member, role, reason="nogif restriction expired")
        logger.info("Lifted nogif restriction for %s (%s)", member, member.id)

    async def _restore_pending(self) -> None:
        """Called on startup — reschedules timers for all active restrictions."""
        await self.bot.wait_until_ready()
        rows = await self.bot.db.get_active_nogif_restrictions()
        if not rows:
            return

        restored = 0
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                continue

            member = guild.get_member(row["user_id"])
            setting_key = f"{SETTING_KEY_PREFIX}.{guild.id}"
            stored_id = await self.bot.db.get_bot_setting(setting_key)
            role = guild.get_role(int(stored_id)) if stored_id else None

            if member is None or role is None:
                # Member left or role was deleted — clean up the stale record.
                await self.bot.db.delete_nogif_restriction(row["user_id"], row["guild_id"])
                continue

            remaining = (row["expires_at"] - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                await self._lift_restriction(member, role, reason="nogif expired (restored)")
            else:
                task = asyncio.create_task(
                    self._scheduled_lift(member, role, remaining),
                    name=f"nogif-lift-{member.id}",
                )
                self._tasks[member.id] = task
                restored += 1

        if restored:
            logger.info("Restored %d pending nogif restriction(s)", restored)

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name="nogif", aliases=["nogifs"])
    @commands.has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def nogif(
        self, ctx: commands.Context, member: discord.Member, duration: str
    ) -> None:
        """Temporarily block a member from sending GIFs/embeds.

        Usage: $nogif @user <duration>
        Duration format: 30s · 10m · 2h · 1d (max 30d)
        """
        # Parse duration
        try:
            seconds, label = _parse_duration(duration)
        except ValueError:
            await ctx.send(
                embed=red_embed(
                    "Formato de duración inválido. Usá: `30s`, `10m`, `2h`, `1d`."
                )
            )
            return

        if seconds > NOGIF_MAX_SECONDS:
            max_days = NOGIF_MAX_SECONDS // 86400
            await ctx.send(
                embed=red_embed(f"La duración máxima es {max_days} días.")
            )
            return

        if seconds <= 0:
            await ctx.send(embed=red_embed("La duración debe ser mayor a 0."))
            return

        # Can't restrict someone with a higher/equal role
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(
                embed=red_embed(
                    "No podés restringir a alguien con un rol igual o más alto que el tuyo."
                )
            )
            return

        if member.bot:
            await ctx.send(embed=red_embed("No se puede aplicar a bots."))
            return

        try:
            role = await self._get_or_create_role(ctx.guild)
        except discord.Forbidden:
            await ctx.send(
                embed=red_embed(
                    "No tengo permiso para crear roles o administrar canales. "
                    "Asegurate de que el bot tenga `Manage Roles` y `Manage Channels`."
                )
            )
            return

        await self._apply_restriction(member, role, seconds, label)

        expires_ts = int((datetime.now(UTC) + timedelta(seconds=seconds)).timestamp())
        await ctx.send(
            embed=green_embed(
                f"🚫 {member.mention} no puede mandar GIFs por **{label}**.\n"
                f"Expira: <t:{expires_ts}:R>"
            )
        )
        logger.info(
            "%s applied nogif to %s (%s) for %s in guild %s",
            ctx.author, member, member.id, label, ctx.guild.id,
        )

    @commands.command(name="ungif")
    @commands.has_permissions(manage_roles=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ungif(self, ctx: commands.Context, member: discord.Member) -> None:
        """Lift a no-GIF restriction early.

        Usage: $ungif @user
        """
        setting_key = f"{SETTING_KEY_PREFIX}.{ctx.guild.id}"
        stored_id = await self.bot.db.get_bot_setting(setting_key)
        role = ctx.guild.get_role(int(stored_id)) if stored_id else None

        has_role = role and role in member.roles
        has_record = await self.bot.db.get_nogif_restriction(member.id, ctx.guild.id)

        if not has_role and not has_record:
            await ctx.send(
                embed=yellow_embed(
                    f"{member.mention} no tiene ninguna restricción activa."
                )
            )
            return

        # Cancel scheduled task
        task = self._tasks.pop(member.id, None)
        if task:
            task.cancel()

        if role and has_role:
            await self._lift_restriction(member, role, reason=f"ungif by {ctx.author}")
        elif has_record:
            await self.bot.db.delete_nogif_restriction(member.id, ctx.guild.id)

        await ctx.send(
            embed=green_embed(
                f"✅ Restricción de GIFs levantada para {member.mention}."
            )
        )
        logger.info(
            "%s lifted nogif restriction for %s (%s) in guild %s",
            ctx.author, member, member.id, ctx.guild.id,
        )

    @nogif.error
    async def nogif_error(self, ctx: commands.Context, error: Exception) -> None:
        if getattr(ctx, "error_handled", False):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                embed=red_embed("Uso: `$nogif @usuario <duración>` — ej: `$nogif @Juan 30m`")
            )
            ctx.error_handled = True
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=red_embed("No encontré ese usuario."))
            ctx.error_handled = True

    @ungif.error
    async def ungif_error(self, ctx: commands.Context, error: Exception) -> None:
        if getattr(ctx, "error_handled", False):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=red_embed("Uso: `$ungif @usuario`"))
            ctx.error_handled = True
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=red_embed("No encontré ese usuario."))
            ctx.error_handled = True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NoGif(bot))
