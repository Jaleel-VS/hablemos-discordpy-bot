"""Slash-command sync must preserve the separation of global and guild scopes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin_cog.main import AdminCog


async def test_guild_sync_preserves_guild_only_commands_without_copying_globals() -> None:
    async with commands.Bot(command_prefix="$", intents=discord.Intents.none(), application_id=123) as bot:
        @app_commands.command(name="e")
        async def vocabulary(interaction: discord.Interaction) -> None:
            """Browse English vocabulary."""

        async def enrich(interaction: discord.Interaction, message: discord.Message) -> None:
            """Enrich a message."""

        guild = discord.Object(id=456)
        bot.tree.add_command(vocabulary)
        bot.tree.add_command(app_commands.ContextMenu(name="VC Enrich", callback=enrich))
        bot.tree.add_command(app_commands.Group(name="league", description="League commands"), guild=guild)
        bot.http.bulk_upsert_guild_commands = AsyncMock(return_value=[])
        bot.http.bulk_upsert_global_commands = AsyncMock(return_value=[])
        ctx = SimpleNamespace(send=AsyncMock(), guild=guild)
        cog = SimpleNamespace(bot=bot)

        for _ in range(2):
            await AdminCog.sync_commands.callback(cog, ctx, guild.id)
            payload = bot.http.bulk_upsert_guild_commands.call_args.kwargs["payload"]
            assert [(command["name"], command["type"]) for command in payload] == [("league", 1)]

        bot.http.bulk_upsert_global_commands.assert_not_awaited()
        await AdminCog.sync_commands.callback(cog, ctx)
        payload = bot.http.bulk_upsert_global_commands.call_args.kwargs["payload"]
        assert {(command["name"], command["type"]) for command in payload} == {("e", 1), ("VC Enrich", 3)}


async def test_activity_entry_point_conflict_does_not_change_guild_commands() -> None:
    async with commands.Bot(command_prefix="$", intents=discord.Intents.none(), application_id=123) as bot:
        error = discord.HTTPException(
            SimpleNamespace(status=400, reason="Bad Request"),
            {"code": 50240, "message": "Activity entry point conflict"},
        )
        bot.http.bulk_upsert_global_commands = AsyncMock(side_effect=error)
        bot.http.bulk_upsert_guild_commands = AsyncMock(return_value=[])
        ctx = SimpleNamespace(send=AsyncMock(), guild=discord.Object(id=456))

        await AdminCog.sync_commands.callback(SimpleNamespace(bot=bot), ctx)

        bot.http.bulk_upsert_guild_commands.assert_not_awaited()
        ctx.send.assert_awaited_once()
