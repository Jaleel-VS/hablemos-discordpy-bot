"""Vocab Catch — a bilingual collectible vocab-card minigame.

A premium Pillow-rendered card spawns in one of the configured channels
after a jittered number of messages (and a cooldown). Each channel has a
**mode** that sets the learner direction:

- Beginner-EN  (``en_to_es``) — card shows English; catch in Spanish.
- Beginner-ES  (``es_to_en``) — card shows Spanish; catch in English.
- General      (``show_es``)  — card shows Spanish; catch in Spanish.

Per-channel spawn state lives in memory (one wild card per channel) and a
per-spawn ``asyncio.Lock`` resolves the catch race so exactly one player
wins. Rarer cards spawn less often (beginner channels skew commoner) and
score more.

Commands: ``$vocadex`` (collection), ``$vocatchtop`` (leaderboard).
Admin group ``$vocatchadmin`` lives in ``admin.py``.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import TYPE_CHECKING, cast

import discord
from discord import Message
from discord.ext import commands

from base_cog import BaseCog
from cogs.utils.embeds import blue_embed

from . import renderer
from .admin import VocabCatchAdmin
from .catch_logic import CardView, answer_matches, points_for, resolve_card
from .config import (
    RARITY_EMBED_COLORS,
    RARITY_LABELS,
    RARITY_POINTS,
    VOCATCH_DESPAWN_S,
    VOCATCH_SPAWN_COOLDOWN_S,
    VOCATCH_SPAWN_EVERY,
    VOCATCH_SPAWN_JITTER,
    channel_modes,
    weights_for_mode,
)
from .renderer import Card

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)


def _render_card(card: Card, view: CardView, *, revealed: bool) -> BytesIO:
    """Type-safe wrapper for ``renderer.render_card``.

    ``render_card`` declares ``view: dict``; a ``CardView`` TypedDict is not
    directly assignable to a plain ``dict`` under the type checker, so cast
    it here (identical at runtime) in one place instead of at each call.
    """
    return renderer.render_card(card, cast(dict, view), revealed=revealed)


@dataclass
class ActiveSpawn:
    """The currently catchable wild card in a channel."""

    card: Card
    view: CardView
    mode: str
    message_id: int
    spawned_at: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    caught: bool = False


@dataclass
class ChannelState:
    """Per-channel spawn pacing + the active wild card (if any)."""

    mode: str
    msg_count: int = 0
    next_threshold: int = 0
    last_spawn: float = 0.0
    active: ActiveSpawn | None = None


class VocabCatch(BaseCog):
    """Spawns and catches bilingual collectible vocab cards."""

    def __init__(self, bot: Hablemos) -> None:
        super().__init__(bot)
        # channel_id -> ChannelState, for each configured (enabled) channel.
        self._channels: dict[int, ChannelState] = {
            cid: ChannelState(mode=mode, next_threshold=self._roll_threshold())
            for cid, mode in channel_modes().items()
        }

    # ── spawn pacing ──

    @staticmethod
    def _roll_threshold() -> int:
        jitter = random.randint(-VOCATCH_SPAWN_JITTER, VOCATCH_SPAWN_JITTER)
        return max(5, VOCATCH_SPAWN_EVERY + jitter)

    def _should_spawn(self, state: ChannelState) -> bool:
        if state.active is not None:
            return False
        if state.msg_count < state.next_threshold:
            return False
        return (time.monotonic() - state.last_spawn) >= VOCATCH_SPAWN_COOLDOWN_S

    # ── listener ──

    @commands.Cog.listener()
    async def on_message(self, message: Message) -> None:
        """Count messages, spawn cards, and resolve catch attempts."""
        if message.author.bot:
            return
        state = self._channels.get(message.channel.id)
        if state is None:
            return

        content = message.content.strip()
        if content.lower().startswith("catch ") and state.active is not None:
            await self._try_catch(message, state, content[len("catch "):].strip())
            return

        state.msg_count += 1
        if self._should_spawn(state):
            await self._spawn(message.channel, state)

    # ── spawning ──

    async def _spawn(self, channel: discord.abc.Messageable, state: ChannelState) -> None:
        """Pick a weighted card, render it for the channel mode, and post."""
        try:
            card = await self.bot.db.get_random_card(weights_for_mode(state.mode))
        except Exception:
            logger.exception("vocatch: failed to fetch a card to spawn")
            return
        if card is None:
            return  # empty pool — nothing to spawn

        view = resolve_card(card, state.mode)
        # get_random_card returns a plain row dict; it carries the Card fields
        # the renderer needs (card_id/pos/gender/rarity).
        card = cast(Card, card)
        try:
            buf = _render_card(card, view, revealed=False)
            file = discord.File(buf, filename="card.png")
            embed = discord.Embed(
                title="✨ A wild word appeared!",
                description="Be the first to type `catch <word>` to add it to "
                            "your collection.",
                color=RARITY_EMBED_COLORS.get(card["rarity"], 0x94A3B8),
            )
            embed.set_image(url="attachment://card.png")
            embed.set_footer(text=f"{RARITY_LABELS.get(card['rarity'], '?')} card")
            msg = await channel.send(embed=embed, file=file)
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("vocatch: failed to post spawn")
            return
        except Exception:
            logger.exception("vocatch: failed to render spawn card")
            return

        state.active = ActiveSpawn(
            card=card, view=view, mode=state.mode,
            message_id=msg.id, spawned_at=time.monotonic())
        state.msg_count = 0
        state.next_threshold = self._roll_threshold()
        state.last_spawn = time.monotonic()
        logger.info("vocatch: spawned card %s (%s, %s) in %s",
                    card["card_id"], view["prompt"], state.mode, msg.channel.id)
        asyncio.create_task(self._despawn_later(msg, state))  # noqa: RUF006

    async def _despawn_later(self, msg: discord.Message, state: ChannelState) -> None:
        spawn = state.active
        await asyncio.sleep(VOCATCH_DESPAWN_S)
        if state.active is spawn and spawn is not None and not spawn.caught:
            state.active = None
            try:
                embed = msg.embeds[0] if msg.embeds else discord.Embed()
                embed.title = "💨 The word got away…"
                embed.description = "Nobody caught it in time."
                await msg.edit(embed=embed)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

    # ── catching ──

    async def _try_catch(self, message: Message, state: ChannelState, guess: str) -> None:
        """Resolve a `catch <guess>` attempt against the channel's spawn."""
        spawn = state.active
        if spawn is None:
            return
        if not answer_matches(guess, spawn.view["answer"],
                              answer_lang=spawn.view["answer_lang"]):
            return  # wrong word — ignore silently (keeps the chat clean)

        async with spawn.lock:
            if spawn.caught or state.active is not spawn:
                return
            spawn.caught = True
            state.active = None

        card = spawn.card
        try:
            count = await self.bot.db.record_catch(message.author.id, card["card_id"])
        except Exception:
            logger.exception("vocatch: failed to record catch for %s", message.author.id)
            spawn.caught = False  # allow a retry
            state.active = spawn
            return

        pts = points_for(card["rarity"])
        await self._announce_catch(message, spawn, count, pts)

    async def _announce_catch(
        self, message: Message, spawn: ActiveSpawn, count: int, pts: int,
    ) -> None:
        """Reveal the card and confirm the catch."""
        card, view = spawn.card, spawn.view
        dup = f" (×{count})" if count > 1 else ""
        try:
            buf = _render_card(card, view, revealed=True)
            file = discord.File(buf, filename="caught.png")
            embed = discord.Embed(
                title=f"🎉 {message.author.display_name} caught **{view['prompt']}**!",
                description=f"**{view['prompt']}** → {view['answer']}\n"
                            f"+{pts} pts · {RARITY_LABELS.get(card['rarity'], '?')}{dup}",
                color=RARITY_EMBED_COLORS.get(card["rarity"], 0x94A3B8),
            )
            embed.set_image(url="attachment://caught.png")
            await message.reply(embed=embed, file=file, mention_author=False)
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("vocatch: failed to announce catch")
        except Exception:
            logger.exception("vocatch: failed to render caught card")

    # ── user commands ──

    @commands.command(name="vocadex")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def vocadex(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        """Show your (or someone's) vocab-card collection."""
        target = member or ctx.author
        collection = await self.bot.db.get_user_collection(target.id, limit=40)
        stats = await self.bot.db.get_collection_stats(target.id)
        if not collection:
            await ctx.send(embed=blue_embed(
                f"{target.display_name} hasn't caught any words yet."))
            return

        points = sum(RARITY_POINTS.get(c["rarity"], 0) * c["count"] for c in collection)
        lines = []
        for c in collection[:25]:
            dup = f" ×{c['count']}" if c["count"] > 1 else ""
            lines.append(
                f"{self._rarity_dot(c['rarity'])} **{c['word_es']}** — "
                f"{c['word_en']}{dup}"
            )
        body = "\n".join(lines)
        if len(collection) > 25:
            body += f"\n*…and {len(collection) - 25} more.*"
        embed = blue_embed(body)
        embed.title = f"📒 {target.display_name}'s Vocadex"
        embed.set_footer(
            text=f"{stats['distinct_cards']} distinct · "
                 f"{stats['total_catches']} caught · {points} pts")
        await ctx.send(embed=embed)

    @commands.command(name="vocatchtop")
    @commands.cooldown(1, 10, commands.BucketType.channel)
    @commands.guild_only()
    async def vocatchtop(self, ctx: commands.Context) -> None:
        """Show the top vocab-card collectors by points."""
        rows = await self.bot.db.get_catch_leaderboard(RARITY_POINTS, limit=10)
        if not rows:
            await ctx.send(embed=blue_embed("No cards have been caught yet."))
            return
        medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
        lines = []
        for i, r in enumerate(rows):
            member = ctx.guild.get_member(r["user_id"]) if ctx.guild else None
            name = member.display_name if member else f"User {r['user_id']}"
            lines.append(
                f"{medals[i]} **{name}** — {int(r['points'])} pts "
                f"({r['distinct_cards']} distinct, {int(r['total_catches'])} caught)")
        embed = blue_embed("\n".join(lines))
        embed.title = "🏆 Top Collectors"
        await ctx.send(embed=embed)

    @staticmethod
    def _rarity_dot(rarity: int) -> str:
        return {1: "⚪", 2: "🟢", 3: "🔵", 4: "🟣", 5: "🟡"}.get(rarity, "⚪")


async def setup(bot: Hablemos) -> None:
    await bot.add_cog(VocabCatch(bot))
    await bot.add_cog(VocabCatchAdmin(bot))
