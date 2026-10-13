"""Recent good news from native English and Spanish publisher RSS feeds."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING

import aiohttp
import asyncpg
import discord
from discord import ui
from discord.ext import commands, tasks

from base_cog import BaseCog
from cogs.goodnews_cog.feeds import FEEDS, fetch_feed

if TYPE_CHECKING:
    from db.news import NewsArticle
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


def build_news_view(article: NewsArticle) -> ui.LayoutView:
    """Show the publisher's RSS teaser, publication date, and original link."""
    spanish = article.language == "es"
    heading = "Buenas noticias" if spanish else "Good news"
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(
        ui.TextDisplay(f"## {heading}\n**{discord.utils.escape_markdown(article.title)}**"),
        ui.Separator(),
        ui.TextDisplay(discord.utils.escape_markdown(article.excerpt)),
        ui.TextDisplay(f"-# {article.source_name} · {article.published_at:%Y-%m-%d}"),
        ui.ActionRow(ui.Button(
            label="Leer noticia" if spanish else "Read article",
            style=discord.ButtonStyle.link,
            url=article.url,
        )),
        accent_colour=discord.Color.teal(),
    ))
    return view


class GoodNews(BaseCog):
    """Read recent optimistic news in English or Spanish, without repeats."""

    session: aiohttp.ClientSession

    async def cog_load(self) -> None:
        """Start periodic feed refreshes without delaying bot startup."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "Hablemos-RSS/1.0 (+https://github.com/Jaleel-VS/hablemos-discordpy-bot)"},
        )
        self.refresh_news.start()

    async def cog_unload(self) -> None:
        """Stop the refresher before closing its HTTP session."""
        task = self.refresh_news.get_task()
        self.refresh_news.cancel()
        if task is not None:
            with suppress(asyncio.CancelledError):
                await task
        await self.session.close()

    @tasks.loop(minutes=30)
    async def refresh_news(self) -> None:
        """Refresh each source independently, preserving cached stories on errors."""
        for feed in FEEDS.values():
            try:
                articles = await fetch_feed(self.session, feed)
                await self.bot.db.store_good_news(articles)
            except (aiohttp.ClientError, TimeoutError, ValueError, asyncpg.PostgresError):
                logger.exception("Good-news refresh failed for %s", feed.source_name)
        try:
            await self.bot.db.prune_good_news()
        except asyncpg.PostgresError:
            logger.exception("Good-news cache cleanup failed")

    @refresh_news.before_loop
    async def before_refresh_news(self) -> None:
        """Wait for the bot to be ready before fetching news."""
        await self.bot.wait_until_ready()

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def goodnews(self, ctx: commands.Context, language: str = "en") -> None:
        """Read a recent, unseen story: $goodnews en or $goodnews es (default: en)."""
        language = language.casefold()
        try:
            if language not in FEEDS:
                self.goodnews.reset_cooldown(ctx)
                await ctx.send(
                    f"Uso / Usage: `{ctx.clean_prefix}goodnews en` / `{ctx.clean_prefix}goodnews es`",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return
            try:
                article = await self.bot.db.next_good_news(ctx.channel.id, language)
            except LookupError:
                message = (
                    "No hay noticias recientes sin leer en este canal. Las fuentes se actualizan cada 30 minutos."
                    if language == "es" else
                    "No unread recent stories are available in this channel. Feeds refresh every 30 minutes."
                )
                await ctx.send(message, allowed_mentions=discord.AllowedMentions.none())
                return
            await ctx.send(view=build_news_view(article), allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.exception("Unable to deliver a good-news response")


async def setup(bot: Hablemos) -> None:
    """Register the auto-discovered good-news cog."""
    await bot.add_cog(GoodNews(bot))
