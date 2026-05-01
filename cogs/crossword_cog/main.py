"""Crossword cog — mini crossword puzzles for language practice."""
import asyncio
import logging
import random
import time
import unicodedata

import discord
from discord import Embed, File, Interaction, app_commands
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

LANG_LABELS = {"es": "🇪🇸 Español", "en": "🇬🇧 English"}


def _normalize(text: str) -> str:
    """Strip accents and lowercase for answer comparison."""
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


class CrosswordGame:
    """State for a single crossword game in a channel.

    ``language`` is the language being practiced — both clues and answers
    are in this language.
    """

    def __init__(
        self,
        grid,
        entries: list[WordEntry],
        language: str,
        difficulty: str,
    ) -> None:
        self.grid = grid
        self.entries = entries  # parallel to grid.placed
        self.language = language  # "es" or "en" — the practice language
        self.difficulty = difficulty
        self.solved: set[int] = set()
        self.solvers: dict[int, str] = {}
        self.revealed_cells: dict[tuple[int, int], str] = {}
        self.started_at = time.monotonic()
        self.starter_id: int = 0
        self.use_v2: bool = False
        self.message: discord.Message | None = None

    @property
    def all_solved(self) -> bool:
        return len(self.solved) == len(self.grid.placed)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def get_answer(self, idx: int) -> str:
        """Get the answer word (same language as clue)."""
        entry = self.entries[idx]
        return entry.word_es if self.language == "es" else entry.word_en

    def get_clue(self, idx: int) -> str:
        """Get the clue (same language as answer)."""
        entry = self.entries[idx]
        return entry.clue_es if self.language == "es" else entry.clue_en

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
            solver = f" — *{self.solvers[idx]}*" if idx in self.solvers else ""
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
        lang_label = LANG_LABELS.get(self.language, self.language)
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


def _parse_args(*args: str) -> tuple[str, str]:
    """Parse difficulty and language from positional args."""
    diff = DEFAULT_DIFFICULTY
    lang = DEFAULT_LANGUAGE
    for arg in args:
        a = arg.lower()
        if a in DIFFICULTIES:
            diff = a
        elif a in ("en", "es", "english", "spanish"):
            lang = "en" if a in ("en", "english") else "es"
    return diff, lang


def _build_v2_view(game: CrosswordGame) -> discord.ui.LayoutView:
    """Build a Components V2 LayoutView for the crossword game."""
    view = discord.ui.LayoutView(timeout=GAME_TIMEOUT_SECONDS)

    diff_cfg = DIFFICULTIES[game.difficulty]
    lang_label = LANG_LABELS.get(game.language, game.language)
    progress = f"{len(game.solved)}/{len(game.grid.placed)}"

    buf = render_grid(game.grid, game.solved, game.revealed_cells)
    view.add_file(File(buf, filename="crossword.png"))

    header = discord.ui.TextDisplay(
        f"## 🧩 Crossword — {diff_cfg.label} · {lang_label}\n"
        f"-# {progress} solved · Type your answers! · ⏱️ {GAME_TIMEOUT_SECONDS // 60}min"
    )

    gallery = discord.ui.MediaGallery(
        discord.MediaGalleryItem(media="attachment://crossword.png"),
    )

    clues = discord.ui.TextDisplay(game.build_clues_text())

    color = discord.Color.green() if game.all_solved else discord.Color.blurple()
    view.add_item(discord.ui.Container(
        header, gallery, discord.ui.Separator(), clues,
        accent_colour=color,
    ))

    return view


def _build_game(
    word_pool: list[WordEntry], difficulty: str, language: str,
) -> CrosswordGame | None:
    """Build a new crossword game.

    ``language`` is the practice language — clues and answers are both
    in this language.
    """
    entries = pick_words(word_pool, difficulty, WORDS_PER_GAME)
    if len(entries) < 3:
        return None

    # Grid words are in the practice language
    answer_words = [
        (e.word_es if language == "es" else e.word_en) for e in entries
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

    async def _start_game(
        self, channel: discord.abc.Messageable, channel_id: int,
        author: discord.User | discord.Member, diff: str, lang: str,
        *, use_v2: bool = False,
    ) -> str | None:
        """Start a crossword game. Returns an error message or None on success."""
        if not self._words:
            return "❌ Word database not loaded yet. Try again in a moment."

        async with self._get_lock(channel_id):
            if channel_id in self._active:
                return "🧩 A crossword is already running in this channel! Solve it first."

            game = _build_game(self._words, diff, lang)
            if game is None:
                return "❌ Failed to generate a crossword. Try again!"

            self._active[channel_id] = game

        game.starter_id = author.id
        game.use_v2 = use_v2
        logger.info(
            "Crossword started by %s in #%s (%s, %s, v2=%s)",
            author, channel_id, diff, lang, use_v2,
        )

        if use_v2:
            view = _build_v2_view(game)
            msg = await channel.send(view=view)
        else:
            embed = game.build_embed()
            img = game.render()
            msg = await channel.send(embed=embed, file=img)

        game.message = msg
        self.bot.loop.create_task(self._timeout_watcher(channel_id))
        return None

    @commands.command(name="crossword", aliases=["cw"])
    @commands.cooldown(1, 10, commands.BucketType.channel)
    async def crossword(
        self, ctx: commands.Context, difficulty: str = "", language: str = "",
    ) -> None:
        """Start a mini crossword puzzle!

        Usage: `$crossword [difficulty] [language]`

        Difficulty: `beginner` (default) or `advanced`
        Language: `es` / `spanish` (default) — practice Spanish
                  `en` / `english` — practice English

        Examples:
          `$crossword` — beginner Spanish
          `$crossword advanced` — advanced Spanish
          `$crossword en` — beginner English
          `$cw advanced english` — advanced English
        """
        diff, lang = _parse_args(difficulty, language)
        err = await self._start_game(ctx.channel, ctx.channel.id, ctx.author, diff, lang)
        if err:
            await ctx.send(err)

    @app_commands.command(name="crossword", description="Start a mini crossword puzzle!")
    @app_commands.describe(
        difficulty="Word difficulty level",
        language="What language are you practicing?",
        style="Message style",
    )
    @app_commands.choices(
        difficulty=[
            app_commands.Choice(name="🟢 Beginner", value="beginner"),
            app_commands.Choice(name="🔴 Advanced", value="advanced"),
        ],
        language=[
            app_commands.Choice(name="🇪🇸 Spanish (clues & answers in Spanish)", value="es"),
            app_commands.Choice(name="🇬🇧 English (clues & answers in English)", value="en"),
        ],
        style=[
            app_commands.Choice(name="Classic (embed + image)", value="classic"),
            app_commands.Choice(name="V2 (components layout)", value="v2"),
        ],
    )
    async def crossword_slash(
        self,
        interaction: Interaction,
        difficulty: str = DEFAULT_DIFFICULTY,
        language: str = DEFAULT_LANGUAGE,
        style: str = "classic",
    ) -> None:
        """Start a mini crossword puzzle with dropdown options."""
        await interaction.response.defer()
        use_v2 = style == "v2"
        err = await self._start_game(
            interaction.channel, interaction.channel.id,
            interaction.user, difficulty, language, use_v2=use_v2,
        )
        if err:
            await interaction.followup.send(err, ephemeral=True)

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
        if not text or len(text) < 2 or len(text) > 50:
            return

        # Quit command — starter or members with manage_messages can end the game
        if text.lower() == "quit":
            can_quit = (
                message.author.id == game.starter_id
                or getattr(message.channel.permissions_for(message.author), "manage_messages", False)
            )
            if can_quit:
                logger.info("Crossword quit by %s in #%s", message.author, channel_id)
                self._active.pop(channel_id, None)
                self._locks.pop(channel_id, None)
                await message.add_reaction("👋")
                await message.channel.send("🧩 Crossword cancelled.")
                return

        idx = game.try_solve(text)
        if idx is None:
            # Only react ❌ on single-word messages (likely intentional guesses)
            if " " not in text and len(text) <= 12:
                await message.add_reaction("❌")
            return

        # Correct answer!
        game.solved.add(idx)
        game.solvers[idx] = message.author.display_name
        pw = game.grid.placed[idx]

        logger.info(
            "Crossword word %s solved by %s in #%s",
            pw.number, message.author, channel_id,
        )

        await message.add_reaction("✅")

        if game.all_solved:
            elapsed = game.elapsed
            await self._end_game(channel_id, completed=True, elapsed=elapsed)
        else:
            try:
                if game.use_v2:
                    view = _build_v2_view(game)
                    msg = await message.channel.send(view=view)
                else:
                    embed = game.build_embed()
                    img = game.render()
                    msg = await message.channel.send(embed=embed, file=img)
                game.message = msg
            except discord.HTTPException:
                logger.warning("Failed to post updated crossword in #%s", channel_id)

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
