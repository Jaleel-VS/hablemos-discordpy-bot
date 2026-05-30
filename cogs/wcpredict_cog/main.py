"""World Cup predictions cog — `/wcpredict` slash command group.

Lets users save a private prediction for the World Cup champion, view
their own pick, and (after the admin grades the result) see a leaderboard
of correct picks. Predictions lock at a configurable deadline.
"""
import logging
from datetime import UTC, datetime

import discord
from discord import Embed, Interaction, app_commands
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed, red_embed, yellow_embed

from .admin import WCPredictAdmin
from .config import (
    SETTING_KEY_DEADLINE,
    SETTING_KEY_WINNER,
    WC_PREDICT_DEFAULT_DEADLINE_TS,
)
from .scoring import score_prediction
from .views import WCPredictMenuView

logger = logging.getLogger(__name__)


def _team_roles(guild: discord.Guild) -> list[discord.Role]:
    """Return guild roles whose name starts with `Team `, alphabetised."""
    return sorted(
        [r for r in guild.roles if r.name.startswith("Team ")],
        key=lambda r: r.name,
    )


class WCPredict(BaseCog):
    """Slash command group `/wcpredict`."""

    group = app_commands.Group(
        name="wcpredict",
        description="Save and view your World Cup champion prediction",
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)

    # ---------- shared helpers ----------

    async def _get_deadline_ts(self) -> int:
        """Return the prediction deadline as a Unix epoch (0 = none)."""
        stored = await self.bot.db.get_bot_setting(SETTING_KEY_DEADLINE)
        if stored is not None:
            return int(stored)
        return WC_PREDICT_DEFAULT_DEADLINE_TS

    async def _is_locked(self) -> tuple[bool, int]:
        """Return (locked?, deadline_ts). 0 deadline ⇒ never locked."""
        deadline_ts = await self._get_deadline_ts()
        if deadline_ts <= 0:
            return False, 0
        now_ts = int(datetime.now(UTC).timestamp())
        return now_ts >= deadline_ts, deadline_ts

    async def _get_winner_role_id(self) -> int | None:
        value = await self.bot.db.get_bot_setting(SETTING_KEY_WINNER)
        return int(value) if value else None

    # ---------- /wcpredict set ----------

    @group.command(name="set", description="Pick or change your World Cup champion prediction")
    async def set_pick(self, interaction: Interaction) -> None:
        guild = interaction.guild
        member = interaction.user

        teams = _team_roles(guild)
        if not teams:
            await interaction.response.send_message(
                embed=red_embed(
                    "No team roles are configured yet. Ask a staff member to set them up."
                ),
                ephemeral=True,
            )
            return

        locked, deadline_ts = await self._is_locked()
        existing = await self.bot.db.get_wc_prediction(member.id)
        current_pick = (
            guild.get_role(existing["team_role_id"]) if existing else None
        )

        if locked:
            if existing is None:
                msg = (
                    f"⏰ Predictions are locked (deadline was <t:{deadline_ts}:F>). "
                    "You didn't lock in a pick this tournament."
                )
            else:
                team_name = current_pick.name if current_pick else existing["team_name"]
                msg = (
                    f"⏰ Predictions are locked (deadline was <t:{deadline_ts}:F>).\n"
                    f"Your locked-in pick: **{team_name}**."
                )
            await interaction.response.send_message(
                embed=yellow_embed(msg), ephemeral=True,
            )
            return

        view = WCPredictMenuView(
            teams=teams,
            user_id=member.id,
            bot=self.bot,
            current_pick=current_pick,
        )
        header = (
            f"Your current pick: **{current_pick.name}**.\nWhat would you like to do?"
            if current_pick
            else "Pick the team you think will win the World Cup."
        )
        if deadline_ts > 0:
            header += f"\nDeadline: <t:{deadline_ts}:R>."
        await interaction.response.send_message(
            content=header, view=view, ephemeral=True,
        )

    # ---------- /wcpredict view ----------

    @group.command(name="view", description="View your current World Cup prediction")
    async def view_pick(self, interaction: Interaction) -> None:
        existing = await self.bot.db.get_wc_prediction(interaction.user.id)
        if existing is None:
            await interaction.response.send_message(
                embed=blue_embed(
                    "You haven't picked a champion yet. Use `/wcpredict set` to lock in your pick."
                ),
                ephemeral=True,
            )
            return

        locked, deadline_ts = await self._is_locked()
        deadline_line = (
            f"\n⏰ Predictions are locked (deadline was <t:{deadline_ts}:F>)."
            if locked
            else (f"\nDeadline: <t:{deadline_ts}:R>." if deadline_ts > 0 else "")
        )
        await interaction.response.send_message(
            embed=blue_embed(
                f"Your World Cup pick: **{existing['team_name']}**."
                f"{deadline_line}"
            ),
            ephemeral=True,
        )

    # ---------- /wcpredict leaderboard ----------

    @group.command(
        name="leaderboard",
        description="See prediction stats (and final standings once graded)",
    )
    async def leaderboard(self, interaction: Interaction) -> None:
        guild = interaction.guild
        winner_role_id = await self._get_winner_role_id()
        rows = await self.bot.db.get_all_wc_predictions(guild.id)
        total = len(rows)

        if total == 0:
            await interaction.response.send_message(
                embed=blue_embed("No predictions have been made yet."),
                ephemeral=True,
            )
            return

        if winner_role_id is None:
            # Pre-grading: distribution only — never reveal individual picks.
            dist = await self.bot.db.wc_prediction_team_distribution(guild.id)
            lines = [
                f"**{name}** — {picks} pick{'s' if picks != 1 else ''}"
                for name, picks in ((r["team_name"], r["picks"]) for r in dist)
            ]
            embed = Embed(
                title="World Cup predictions so far",
                description="\n".join(lines) or "No picks yet.",
                color=discord.Color.blurple(),
            )
            embed.set_footer(
                text=f"{total} prediction{'s' if total != 1 else ''} • "
                "Individual picks revealed after the champion is set.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Graded: show full standings.
        winner_role = guild.get_role(winner_role_id)
        winner_name = winner_role.name if winner_role else f"<role:{winner_role_id}>"

        winners: list[str] = []
        losers: list[str] = []
        for r in rows:
            user = guild.get_member(r["user_id"]) or self.bot.get_user(r["user_id"])
            display = user.mention if user else f"<@{r['user_id']}>"
            points = score_prediction(r["team_role_id"], winner_role_id)
            line = f"{display} — {r['team_name']}"
            if points > 0:
                winners.append(f"✅ {line}")
            else:
                losers.append(f"❌ {line}")

        embed = Embed(
            title=f"World Cup predictions — Champion: {winner_name}",
            color=discord.Color.gold(),
        )
        if winners:
            embed.add_field(
                name=f"Correct ({len(winners)})",
                value="\n".join(winners[:25]) or "—",
                inline=False,
            )
        if losers:
            embed.add_field(
                name=f"Incorrect ({len(losers)})",
                value="\n".join(losers[:25]) or "—",
                inline=False,
            )
        if len(winners) > 25 or len(losers) > 25:
            embed.set_footer(text="Showing first 25 of each group.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WCPredict(bot))
    await bot.add_cog(WCPredictAdmin(bot))

