"""Prefix command for market and household purchasing-power comparisons."""
from __future__ import annotations

import asyncio
import logging
import shlex
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from base_cog import BaseCog
from cogs.ppp_cog.calculator import calculate, parse_amount
from cogs.ppp_cog.client import PPPClient
from cogs.ppp_cog.countries import resolve_location
from cogs.ppp_cog.models import PPPError, PPPInputError
from cogs.ppp_cog.renderer import render_ppp_card

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)

USAGE = (
    "$ppp <amount> <from> <to>\n"
    "Examples:\n"
    "`$ppp 7000 ZAR USD`\n"
    "`$ppp 1000 Colombia United States`\n"
    "`$ppp 1000 EUR:France USD`"
)


def parse_command_arguments(argument: str) -> tuple[str, str, str]:
    """Parse three shell-like PPP command arguments."""
    try:
        parts = shlex.split(argument)
    except ValueError as exc:
        raise PPPInputError("I couldn't read those arguments. Check your quotation marks.") from exc
    if len(parts) < 3:
        raise PPPInputError(f"Please provide an amount, source, and target.\n\n{USAGE}")
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]

    # Multi-word country names are accepted when quoted. Without quotes there
    # is no reliable boundary between source and target, so explain the fix.
    raise PPPInputError(
        "Country names containing spaces must be quoted, for example "
        "`$ppp 1000 \"South Africa\" \"United States\"`."
    )


class PurchasingPower(BaseCog):
    """Compare market conversion with household purchasing power."""

    def __init__(self, bot: Hablemos):
        super().__init__(bot)
        self.client = PPPClient()

    async def cog_unload(self) -> None:
        """Release the shared API session when the cog unloads."""
        await self.client.close()

    @commands.command(name="ppp", aliases=["purchasingpower"])
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def ppp(self, ctx: commands.Context, *, argument: str = "") -> None:
        """Compare a market conversion with household purchasing power."""
        if not argument.strip() or argument.strip().casefold() == "help":
            await ctx.send(
                "**Purchasing-power calculator**\n"
                f"{USAGE}\n\n"
                "Currencies default to their most commonly associated country. "
                "Use `CURRENCY:Country` to override a shared currency."
            )
            return

        try:
            amount_text, source_text, target_text = parse_command_arguments(argument)
            amount = parse_amount(amount_text)
            source_country = resolve_location(source_text)
            target_country = resolve_location(target_text)
            if source_country == target_country:
                raise PPPInputError("Choose two different countries to compare.")

            async with ctx.typing():
                source_ppp, target_ppp, market = await asyncio.gather(
                    self.client.get_ppp(source_country),
                    self.client.get_ppp(target_country),
                    self.client.get_market_rate(
                        source_country.currency,
                        target_country.currency,
                    ),
                )
                result = calculate(amount, source_ppp, target_ppp, market)
                buffer = await asyncio.wait_for(
                    asyncio.to_thread(render_ppp_card, result),
                    timeout=20,
                )

            filename = (
                f"ppp-{source_country.territory.lower()}-"
                f"{target_country.territory.lower()}.png"
            )
            await ctx.send(file=discord.File(buffer, filename=filename))
        except PPPError as exc:
            await ctx.send(f"⚠️ {exc}")
        except TimeoutError:
            await ctx.send("⚠️ The comparison took too long to render. Please try again.")
        except Exception:
            logger.exception("Unexpected PPP command failure")
            await ctx.send("⚠️ I couldn't calculate that comparison right now. Please try again later.")


async def setup(bot: Hablemos) -> None:
    """Load the purchasing-power cog."""
    await bot.add_cog(PurchasingPower(bot))
