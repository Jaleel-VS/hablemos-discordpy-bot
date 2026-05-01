"""Crossword cog — mini crossword puzzles for language practice."""
import asyncio
import logging
import random
import time
import unicodedata

import discord
from discord import Embed, File
from discord.ext import commands

from base_cog import BaseCog

from .config import (
    DEFAULT_DIFFICULTY,
    DEFAULT_LANGUAGE,
    DIFFICULTIES,
    GAME_TIMEOUT_SECONDS,
    WORDS_PER_GAME,
)
from .grid import generate_grid
from .renderer import render_grid
from .words import WordEntry, load_words_from_db, pick_words

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Strip accents and lowercase for answer comparison."""
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


class CrosswordGame:
    """State for a single crossword game in a channel."""

    def __init__(
        self,
        grid,
        entries: list[WordEntry],
        language: str,
        difficulty: str,
    ) -> None:
        self.grid = grid
        self.entries = entries  # parallel to grid.placed
        self.language = language
        self.difficulty = difficulty
        self.solved: set[int] = set()
        self.solvers: dict[int, str] = {}  # word index -> display_name
        self.revealed_cells: dict[tuple[int, int], str] = {}
        self.started_at = time.monotonic()
        self.starter_id: int = 0
        self.message: discord.Message | None = None

    @property
    def all_solved(self) -> bool:
        return len(self.solved) == len(self.grid.placed)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def answer_word(self) -> str:
        """Return 'es' or 'en' — the language of the answer."""
        return "es" if self.language == "en" else "en"

    def get_answer(self, idx: int) -> str:
        """Get the answer word for a placed word by index."""
        entry = self.entries[idx]
        return entry.word_es if self.answer_word() == "es" else entry.word_en

    def get_clue(self, idx: int) -> str:
        """Get the clue for a placed word by index."""
        entry = self.entries[idx]
        return entry.clue_en if self.language == "en" else entry.clue_es

    def try_solve(self, text: str) -> int | None:
        """Try to match *text* against unsolved words. Return index or None."""
        norm = _normalize(text)
        for idx, _pw in enumerate(self.grid.placed):
            if idx in self.solved:
                continue
            if _normalize(self.get_answer(idx)) == norm:
                return idx
        return None

    def build_clues_text(self) -> str:
        """Build the clue list for the embed."""
        across: list[str] = []
        down: list[str] = []

        for idx, pw in enumerate(self.grid.placed):
            status = "✅" if idx in self.solved else f"({len(pw.word)})"
            solver = f" — *{self.solvers[idx]}*" if idx in self.solved else ""
            line = f"**{pw.number}.** {self.get_clue(idx)} {status}{solver}"

            if pw.direction == "across":
                across.append(line)
            else:
                down.append(line)

        parts: list[str] = []
        if across:
            parts.append("**➡️ Across**\n" + "\n".join(across))
        if down:
            parts.append("**⬇️ Down**\n" + "\n".join(down))
        return "\n\n".join(parts)

    def build_embed(self) -> Embed:
        """Build the game embed with clues."""
        diff_cfg = DIFFICULTIES[self.difficulty]
        lang_label = "EN → ES" if self.language == "en" else "ES → EN"
        progress = f"{len(self.solved)}/{len(self.grid.placed)}"

        embed = Embed(
            title=f"🧩 Crossword — {diff_cfg.label} · {lang_label}",
            description=self.build_clues_text(),
            color=discord.Color.green() if self.all_solved else discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"{progress} solved · Type your answers! · ⏱️ {GAME_TIMEOUT_SECONDS // 60}min",
        )
        embed.set_image(url="attachment://crossword.png")
        return embed

    def render(self) -> File:
        """Render the grid image as a discord.File."""
        buf = render_grid(self.grid, self.solved, self.revealed_cells)
        return File(buf, filename="crossword.png")


def _build_game(
    word_pool: list[WordEntry], difficulty: str, language: str,
) -> CrosswordGame | None:
    """Build a new crossword game. Returns None on grid generation failure."""
    entries = pick_words(word_pool, difficulty, WORDS_PER_GAME)
    if len(entries) < 3:
        return None

    # Determine answer words (what goes on the grid)
    answer_lang = "es" if language == "en" else "en"
    answer_words = [
        (e.word_es if answer_lang == "es" else e.word_en) for e in entries
    ]

    grid = generate_grid(answer_words)
    if grid is None:
        return None

    # Map grid.placed order back to entries — grid may reorder words
    ordered_entries: list[WordEntry] = []
    used: set[int] = set()
    for pw in grid.placed:
        norm_pw = _normalize(pw.word)
        for j, aw in enumerate(answer_words):
            if j not in used and _normalize(aw) == norm_pw:
                ordered_entries.append(entries[j])
                used.add(j)
                break

    if len(ordered_entries) != len(grid.placed):
        return None

    game = CrosswordGame(grid, ordered_entries, language, difficulty)

    # Pre-reveal letters for beginner
    diff_cfg = DIFFICULTIES[difficulty]
    if diff_cfg.reveal_fraction > 0:
        for pw in grid.placed:
            cells = pw.cells
            n_reveal = max(1, int(len(cells) * diff_cfg.reveal_fraction))
            reveal_positions = random.sample(range(len(cells)), n_reveal)
            for pos in reveal_positions:
                r, c = cells[pos]
                game.revealed_cells[(r, c)] = pw.word[pos]

    return game


class CrosswordCog(BaseCog):
    """Mini crossword puzzles for Spanish/English practice."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self._active: dict[int, CrosswordGame] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._words: list[WordEntry] = []

    async def cog_load(self) -> None:
        """Load word pool from the database on startup."""
        self._words = await load_words_from_db(self.bot.db.pool)
        logger.info("Crossword cog loaded with %s words", len(self._words))

    def _get_lock(self, channel_id: int) -> asyncio.Lock:
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()
        return self._locks[channel_id]

    @commands.command(name="crossword", aliases=["cw"])
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def crossword(
        self, ctx: commands.Context, difficulty: str = "", language: str = "",
    ) -> None:
        """Start a mini crossword puzzle!

        Usage: `$crossword [difficulty] [language]`

        Difficulty: `beginner` (default) or `advanced`
        Language: `en` (English clues → Spanish answers, default)
                  `es` (Spanish clues → English answers)

        Examples:
          `$crossword` — beginner, English clues
          `$crossword advanced es` — advanced, Spanish clues
          `$cw` — shortcut
        """
        channel_id = ctx.channel.id

        if not self._words:
            await ctx.send("❌ Word database not loaded yet. Try again in a moment.")
            return

        # Parse args — allow either order
        diff = DEFAULT_DIFFICULTY
        lang = DEFAULT_LANGUAGE
        for arg in (difficulty.lower(), language.lower()):
            if arg in DIFFICULTIES:
                diff = arg
            elif arg in ("en", "es"):
                lang = arg

        async with self._get_lock(channel_id):
            if channel_id in self._active:
                await ctx.send("🧩 A crossword is already running in this channel! Solve it first.")
                return

            game = _build_game(self._words, diff, lang)
            if game is None:
                await ctx.send("❌ Failed to generate a crossword. Try again!")
                return

            self._active[channel_id] = game

        game.starter_id = ctx.author.id
        logger.info(
            "Crossword started by %s in #%s (%s, %s)",
            ctx.author, channel_id, diff, lang,
        )

        embed = game.build_embed()
        img = game.render()
        msg = await ctx.send(embed=embed, file=img)
        game.message = msg

        # Start timeout watcher
        self.bot.loop.create_task(self._timeout_watcher(channel_id))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Listen for answers in channels with active games."""
        if message.author.bot:
            return

        channel_id = message.channel.id
        game = self._active.get(channel_id)
        if game is None:
            return

        # Ignore command invocations
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        text = message.content.strip()
        if not text or len(text) > 50:
            return

        # Quit command — starter or members with manage_messages can end the game
        if text.lower() == "quit":
            can_quit = (
                message.author.id == game.starter_id
                or getattr(message.channel.permissions_for(message.author), "manage_messages", False)
            )
            if can_quit:
                logger.info("Crossword quit by %s in #%s", message.author, channel_id)
                await self._end_game(channel_id, completed=False)
                await message.add_reaction("👋")
                return

        idx = game.try_solve(text)
        if idx is None:
            return

        # Correct answer!
        game.solved.add(idx)
        game.solvers[idx] = message.author.display_name
        pw = game.grid.placed[idx]

        logger.info(
            "Crossword word %s solved by %s in #%s",
            pw.number, message.author, channel_id,
        )

        if game.all_solved:
            elapsed = game.elapsed
            await self._end_game(channel_id, completed=True, elapsed=elapsed)
            await message.add_reaction("🎉")
        else:
            await message.add_reaction("✅")
            try:
                embed = game.build_embed()
                img = game.render()
                if game.message:
                    await game.message.edit(embed=embed, attachments=[img])
            except discord.HTTPException:
                logger.warning("Failed to update crossword message in #%s", channel_id)

    async def _end_game(
        self, channel_id: int, *, completed: bool, elapsed: float = 0,
    ) -> None:
        """End a game and post results."""
        game = self._active.pop(channel_id, None)
        self._locks.pop(channel_id, None)
        if game is None:
            return

        if completed:
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)

            solver_counts: dict[str, int] = {}
            for name in game.solvers.values():
                solver_counts[name] = solver_counts.get(name, 0) + 1
            ranking = sorted(solver_counts.items(), key=lambda t: -t[1])
            solver_text = "\n".join(
                f"**{name}** — {count} word{'s' if count > 1 else ''}"
                for name, count in ranking
            )

            embed = Embed(
                title="🧩 Crossword Complete! 🎉",
                description=f"Solved in **{minutes}m {seconds}s**\n\n{solver_text}",
                color=discord.Color.green(),
            )
            img = game.render()
            embed.set_image(url="attachment://crossword.png")

            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(embed=embed, file=img)
        else:
            for idx in range(len(game.grid.placed)):
                game.solved.add(idx)

            embed = Embed(
                title="🧩 Crossword — Time's Up! ⏱️",
                description=game.build_clues_text(),
                color=discord.Color.orange(),
            )
            img = game.render()
            embed.set_image(url="attachment://crossword.png")

            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(embed=embed, file=img)

    async def _timeout_watcher(self, channel_id: int) -> None:
        """End the game after the timeout period."""
        await asyncio.sleep(GAME_TIMEOUT_SECONDS)
        if channel_id in self._active:
            logger.info("Crossword timed out in #%s", channel_id)
            await self._end_game(channel_id, completed=False)

    async def cog_unload(self) -> None:
        """Clean up active games on cog unload."""
        self._active.clear()
        self._locks.clear()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CrosswordCog(bot))
