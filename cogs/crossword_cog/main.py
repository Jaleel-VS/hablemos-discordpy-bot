"""Crossword cog — mini crossword puzzles for language practice."""
import asyncio
import logging
import random
import time
import unicodedata
import uuid
from datetime import UTC, datetime

import discord
from discord import Embed, File, Interaction, app_commands
from discord.ext import commands

from base_cog import BaseCog

from .config import (
    DEFAULT_DIFFICULTY,
    DEFAULT_LANGUAGE,
    DIFFICULTIES,
    GAME_TIMEOUT_SECONDS,
    WORDS_PER_GAME_MAX,
    WORDS_PER_GAME_MIN,
)
from .grid import generate_grid
from .renderer import render_grid
from .words import WordEntry, load_words_from_db, pick_words

logger = logging.getLogger(__name__)

LANG_LABELS = {"es": "🇪🇸 Español", "en": "🇬🇧 English"}


def _normalize(text: str) -> str:
    """Strip accents, punctuation, and lowercase for answer comparison."""
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c) and c.isalnum())


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
        # Parallel to ``solvers``: user_id per solved word, used for metrics.
        self.solver_ids: dict[int, int] = {}
        # Monotonic seconds from game start when each word was solved.
        self.word_solved_at: dict[int, float] = {}
        # Word indices that received a hint-revealed cell.
        self.word_hints: set[int] = set()
        self.revealed_cells: dict[tuple[int, int], str] = {}
        self.started_at = time.monotonic()
        # Wall-clock start for DB persistence.
        self.started_at_wall: datetime = datetime.now(UTC)
        self.starter_id: int = 0
        self.channel_id: int = 0
        self.guild_id: int | None = None
        self.game_id: uuid.UUID = uuid.uuid4()
        self.use_v2: bool = False
        self.message: discord.Message | None = None
        self.hints_used: int = 0
        self.scores: dict[int, int] = {}  # user_id -> points
        self.scores_names: dict[int, str] = {}  # user_id -> display_name

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

    def use_hint(self) -> str | None:
        """Reveal one random unrevealed cell. Returns the word hint was for, or None."""
        if self.hints_used >= 2:
            return None
        # Collect all cells already visible (solved words + pre-revealed)
        visible: set[tuple[int, int]] = set(self.revealed_cells.keys())
        for sidx in self.solved:
            for r, c in self.grid.placed[sidx].cells:
                visible.add((r, c))
        # Find unsolved words with truly hidden cells
        for idx, pw in enumerate(self.grid.placed):
            if idx in self.solved:
                continue
            hidden = [
                (i, r, c) for i, (r, c) in enumerate(pw.cells)
                if (r, c) not in visible
            ]
            if hidden:
                pos, r, c = random.choice(hidden)
                self.revealed_cells[(r, c)] = pw.word[pos]
                self.hints_used += 1
                self.word_hints.add(idx)
                return self.get_answer(idx)
        return None

    def build_clues_text(self, *, show_answers: bool = False) -> str:
        """Build the clue list for the embed."""
        across: list[str] = []
        down: list[str] = []

        for idx, pw in enumerate(self.grid.placed):
            if idx in self.solvers:
                status = f"✅ — *{self.solvers[idx]}*"
            elif show_answers:
                status = f"💡 **{self.get_answer(idx)}**"
            elif idx in self.solved:
                status = "✅"
            else:
                status = f"({len(pw.word)})"
            line = f"**{pw.number}.** {self.get_clue(idx)} {status}"

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

    def _time_remaining(self) -> str:
        """Human-readable time remaining."""
        remaining = max(0, GAME_TIMEOUT_SECONDS - self.elapsed)
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        return f"{minutes}:{seconds:02d}"

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
            text=f"{progress} solved · ⏱️ {self._time_remaining()} remaining · Type 'quit' to cancel",
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


def _build_v2_view(game: CrosswordGame) -> tuple[discord.ui.LayoutView, File]:
    """Build a Components V2 LayoutView for the crossword game.

    Returns (view, file) — file must be passed to send() separately.
    """
    view = discord.ui.LayoutView(timeout=GAME_TIMEOUT_SECONDS)

    diff_cfg = DIFFICULTIES[game.difficulty]
    lang_label = LANG_LABELS.get(game.language, game.language)
    progress = f"{len(game.solved)}/{len(game.grid.placed)}"

    buf = render_grid(game.grid, game.solved, game.revealed_cells)
    file = File(buf, filename="crossword.png")

    header = discord.ui.TextDisplay(
        f"## 🧩 Crossword — {diff_cfg.label} · {lang_label}\n"
        f"-# {progress} solved · ⏱️ {game._time_remaining()} remaining · Type 'quit' to cancel"
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

    return view, file


def _build_game(
    word_pool: list[WordEntry], difficulty: str, language: str,
) -> CrosswordGame | None:
    """Build a new crossword game.

    ``language`` is the practice language — clues and answers are both
    in this language.  Retries with fresh words if grid generation fails.
    """
    for _attempt in range(5):
        n_words = random.randint(WORDS_PER_GAME_MIN, WORDS_PER_GAME_MAX)
        entries = pick_words(word_pool, difficulty, n_words)
        if len(entries) < 3:
            return None

        answer_words = [
            (e.word_es if language == "es" else e.word_en) for e in entries
        ]

        # Filter out multi-word or overly long answers (can't place on grid)
        valid = [
            (aw, e) for aw, e in zip(answer_words, entries, strict=True)
            if " " not in aw and len(aw) <= 13
        ]
        if len(valid) < 3:
            continue
        answer_words = [aw for aw, _ in valid]
        entries = [e for _, e in valid]

        grid = generate_grid(answer_words)
        if grid is None:
            continue

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
            continue

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

    return None


class CrosswordCog(BaseCog):
    """Mini crossword puzzles for Spanish/English practice."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self._active: dict[int, CrosswordGame] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._watchers: dict[int, asyncio.Task] = {}
        self._words: list[WordEntry] = []

    async def cog_load(self) -> None:
        """Load word pool from the database on startup, then notify any
        players whose games were interrupted by a previous bot shutdown."""
        self._words = await load_words_from_db(self.bot.db.pool)
        logger.info("Crossword cog loaded with %s words", len(self._words))
        await self._recover_interrupted_games()

    async def _recover_interrupted_games(self) -> None:
        """Post a “game interrupted” notice for each stale active-game row.

        Resolves the original channel (guild channel / thread / DM) and
        sends a single message explaining the interruption, then deletes
        the row. Best-effort: failures per row are logged but don't stop
        processing of the others.
        """
        try:
            rows = await self.bot.db.crossword_get_all_active_games()
        except Exception:
            logger.exception("Failed to fetch interrupted crossword games")
            return

        if not rows:
            return

        logger.info("Recovering %d interrupted crossword game(s)", len(rows))
        for row in rows:
            channel_id = row["channel_id"]
            try:
                await self._notify_interrupted(row)
            except Exception:
                logger.exception(
                    "Failed to notify interrupted crossword game in channel %s",
                    channel_id,
                )
            finally:
                try:
                    await self.bot.db.crossword_clear_active_game(channel_id)
                except Exception:
                    logger.exception(
                        "Failed to clear interrupted crossword row for channel %s",
                        channel_id,
                    )

    async def _notify_interrupted(self, row) -> None:
        """Send a single interrupt-recovery message for one stale game row."""
        channel_id: int = row["channel_id"]
        starter_id: int = row["starter_id"]
        is_dm: bool = row["is_dm"]
        solved: int = row["solved_count"]
        total: int = row["total_words"]
        lang_label = LANG_LABELS.get(row["language"], row["language"])
        diff_cfg = DIFFICULTIES.get(row["difficulty"])
        diff_label = diff_cfg.label if diff_cfg else row["difficulty"]

        # Resolve a Messageable: guild channel/thread via cache, DM via user.
        target: discord.abc.Messageable | None = None
        if not is_dm:
            target = self.bot.get_channel(channel_id)
            if target is None:
                # Thread may be uncached; try to fetch.
                try:
                    target = await self.bot.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    target = None

        if target is None:
            # Either a DM or a channel we can't see anymore — DM the starter.
            try:
                user = await self.bot.fetch_user(starter_id)
                target = await user.create_dm()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Could not reach channel %s or starter %s to notify interrupt",
                    channel_id, starter_id,
                )
                return

        embed = Embed(
            title="⚠️ Crossword interrupted",
            description=(
                f"Your crossword was interrupted by a bot restart and "
                f"couldn't be resumed. Sorry about that!\n\n"
                f"**Progress:** {solved}/{total} words solved\n"
                f"**Puzzle:** {diff_label} · {lang_label}\n\n"
                f"Run `/crossword` (or `$crossword`) to start a new one."
            ),
            color=discord.Color.orange(),
        )

        try:
            await target.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Failed to send interrupt notice for channel %s", channel_id,
            )

        # Log an 'interrupted' row in crossword_games so stats reflect
        # restart-induced losses. No participant / word-event detail is
        # available here — we only have what the active-game snapshot saved.
        try:
            await self.bot.db.crossword_record_interrupted(
                game_id=row["game_id"],
                guild_id=row["guild_id"],
                channel_id=channel_id,
                starter_id=starter_id,
                difficulty=row["difficulty"],
                language=row["language"],
                total_words=total,
                words_solved=solved,
                started_at=row["started_at"],
                ended_at=datetime.now(UTC),
            )
        except Exception:
            logger.debug(
                "Failed to record interrupted crossword game for channel %s",
                channel_id, exc_info=True,
            )

    def _get_lock(self, channel_id: int) -> asyncio.Lock:
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()
        return self._locks[channel_id]

    async def _start_game(
        self, channel: discord.abc.Messageable, channel_id: int,
        author: discord.User | discord.Member, diff: str, lang: str,
        *, use_v2: bool = False, followup: discord.Webhook | None = None,
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
        game.channel_id = channel_id
        game.guild_id = getattr(getattr(channel, "guild", None), "id", None)
        # Components v2 not supported in DMs
        game.use_v2 = use_v2 and getattr(channel, "guild", None) is not None
        logger.info(
            "Crossword started by %s in #%s (%s, %s, v2=%s, channel_type=%s, guild=%s)",
            author, channel_id, diff, lang, game.use_v2,
            type(channel).__name__, getattr(channel, "guild", "NO_ATTR"),
        )

        if use_v2:
            view, file = _build_v2_view(game)
            if followup:
                msg = await followup.send(view=view, file=file, wait=True)
            else:
                msg = await channel.send(view=view, file=file)
        else:
            embed = game.build_embed()
            img = game.render()
            if followup:
                msg = await followup.send(embed=embed, file=img, wait=True)
            else:
                msg = await channel.send(embed=embed, file=img)

        game.message = msg

        # Persist a minimal snapshot so we can notify the player if the
        # bot restarts before the game ends.
        is_dm = getattr(channel, "guild", None) is None
        guild_id = getattr(getattr(channel, "guild", None), "id", None)
        try:
            await self.bot.db.crossword_save_active_game(
                channel_id=channel_id,
                starter_id=author.id,
                guild_id=guild_id,
                is_dm=is_dm,
                message_id=getattr(msg, "id", None),
                language=lang,
                difficulty=diff,
                total_words=len(game.grid.placed),
                game_id=game.game_id,
            )
        except Exception:
            logger.exception(
                "Failed to persist crossword active-game snapshot for #%s",
                channel_id,
            )

        # Threads need an explicit join() so the bot receives on_message events
        if isinstance(channel, discord.Thread):
            try:
                await channel.join()
            except discord.HTTPException:
                logger.warning("Failed to join thread #%s", channel_id)

        self._watchers[channel_id] = self.bot.loop.create_task(self._timeout_watcher(channel_id))
        return None

    @commands.command(name="crossword", aliases=["cw"])
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
    )
    async def crossword_slash(
        self,
        interaction: Interaction,
        difficulty: str = DEFAULT_DIFFICULTY,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        """Start a mini crossword puzzle with dropdown options."""
        await interaction.response.defer()
        err = await self._start_game(
            interaction.channel, interaction.channel.id,
            interaction.user, difficulty, language,
            use_v2=True, followup=interaction.followup,
        )
        if err:
            await interaction.followup.send(err, ephemeral=True)

    @commands.command(name="cwtimeout")
    @commands.is_owner()
    async def set_timeout(self, ctx: commands.Context, seconds: int = GAME_TIMEOUT_SECONDS):
        """Owner-only: override crossword timeout. $cwtimeout 30"""
        self._timeout_override = seconds
        await ctx.send(f"⏱️ Crossword timeout set to **{seconds}s**.")

    @commands.command(name="cwstats")
    @commands.is_owner()
    async def cwstats(self, ctx: commands.Context, scope: str = "30") -> None:
        """Owner-only: show aggregate crossword stats.

        Usage:
          `$cwstats`        — last 30 days
          `$cwstats <N>`    — last N days (1–365)
          `$cwstats all`    — lifetime
        """
        if scope.lower() in ("all", "lifetime", "∞"):
            days: int | None = None
            window_label = "lifetime"
        else:
            try:
                days = max(1, min(int(scope), 365))
            except ValueError:
                return await ctx.send("❌ Usage: `$cwstats [days|all]`")
            window_label = f"last {days}d"

        stats = await self.bot.db.crossword_get_stats(days=days)
        totals = stats["totals"]
        players = stats["players"]
        games = int(totals.get("games") or 0)

        if games == 0:
            return await ctx.send(f"ℹ️ No crossword games recorded ({window_label}).")

        breakdown = stats["breakdown"]
        top = await self.bot.db.crossword_get_top_solvers(days=days, limit=10)

        completed = int(totals.get("completed") or 0)
        timed_out = int(totals.get("timed_out") or 0)
        quit_ct = int(totals.get("quit") or 0)
        interrupted = int(totals.get("interrupted") or 0)
        completion_rate = (completed / games * 100) if games else 0.0
        avg_ratio = float(totals.get("avg_completion_ratio") or 0) * 100
        avg_secs = float(totals.get("avg_completion_seconds") or 0)
        avg_min, avg_sec = divmod(int(avg_secs), 60)

        embed = Embed(
            title=f"🧩 Crossword Stats ({window_label})",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="📊 Games",
            value=(
                f"**Games played:** {games:,}\n"
                f"**Unique players:** {int(players.get('unique_players') or 0):,}\n"
                f"**Avg participants/game:** {float(players.get('avg_participants_per_game') or 0):.1f}\n"
                f"**Words solved:** {int(totals.get('total_words_solved') or 0):,}\n"
                f"**Avg completion:** {avg_ratio:.1f}%\n"
                f"**Avg time (full):** {avg_min}m {avg_sec:02d}s\n"
                f"**Total hints used:** {int(totals.get('total_hints') or 0):,} "
                f"(avg {float(totals.get('avg_hints_per_game') or 0):.2f}/game)"
            ),
            inline=False,
        )
        embed.add_field(
            name="🏁 Completion",
            value=(
                f"✅ Completed: **{completed}** ({completion_rate:.1f}%)\n"
                f"⏱️ Timed out: **{timed_out}**\n"
                f"👋 Quit: **{quit_ct}**\n"
                f"⚠️ Interrupted: **{interrupted}**"
            ),
            inline=False,
        )

        if breakdown:
            lines = []
            for r in breakdown:
                diff_cfg = DIFFICULTIES.get(r["difficulty"])
                diff_label = diff_cfg.label if diff_cfg else r["difficulty"]
                lang_label = LANG_LABELS.get(r["language"], r["language"])
                b_games = int(r["games"])
                b_completed = int(r["completed"])
                rate = (b_completed / b_games * 100) if b_games else 0.0
                lines.append(
                    f"• {diff_label} · {lang_label} — "
                    f"{b_games:,} games, {b_completed} completed ({rate:.0f}%)"
                )
            embed.add_field(name="🔹 Breakdown", value="\n".join(lines), inline=False)

        if top:
            lines = [
                f"**{i}.** {r['display_name']} — {int(r['words_solved']):,} words · "
                f"{int(r['games'])} games · {int(r['games_started'])} started"
                for i, r in enumerate(top, 1)
            ]
            embed.add_field(name="🏅 Top Solvers", value="\n".join(lines), inline=False)

        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        logger.info(
            "Admin %s viewed cwstats (%s, %d games)",
            ctx.author, window_label, games,
        )

    @commands.command(name="cwwords")
    @commands.is_owner()
    async def cwwords(
        self,
        ctx: commands.Context,
        mode: str = "hardest",
        language: str = "",
        limit: int = 15,
    ) -> None:
        """Owner-only: show per-word solve-rate stats from game data.

        Usage:
          `$cwwords hardest [lang] [limit]` — lowest solve rate first
          `$cwwords easiest [lang] [limit]` — highest solve rate first
          `$cwwords unseen  <lang> [limit]` — word-list entries that never appeared

        `lang` is optional for hardest/easiest, required for unseen; use
        `es` or `en`.
        """
        mode = mode.lower()
        lang_arg = language.lower() if language else None
        if lang_arg in ("english",):
            lang_arg = "en"
        elif lang_arg in ("spanish",):
            lang_arg = "es"
        if lang_arg not in (None, "es", "en"):
            return await ctx.send("❌ Language must be `es` or `en`.")
        limit = max(1, min(limit, 25))

        if mode in ("hardest", "easiest"):
            rows = await self.bot.db.crossword_get_word_difficulty(
                language=lang_arg,
                order=mode,
                min_appearances=3,
                limit=limit,
            )
            if not rows:
                return await ctx.send(
                    "ℹ️ Not enough per-word data yet — need words that have "
                    "appeared in at least 3 games."
                )
            lines: list[str] = []
            for i, r in enumerate(rows, 1):
                rate = float(r["solve_rate"]) * 100
                avg_sec = r["avg_solve_seconds"]
                avg_str = (
                    f" · avg {int(avg_sec)}s" if avg_sec is not None else ""
                )
                hints = int(r["hint_assists"])
                hint_str = f" · {hints} hint-assist{'s' if hints != 1 else ''}" if hints else ""
                lang_tag = LANG_LABELS.get(r["language"], r["language"])
                lines.append(
                    f"**{i}.** `{r['word']}` ({lang_tag} · {r['difficulty']}) — "
                    f"{rate:.0f}% solved ({int(r['solves'])}/{int(r['appearances'])})"
                    f"{avg_str}{hint_str}"
                )
            title_scope = "" if lang_arg is None else f" · {LANG_LABELS.get(lang_arg, lang_arg)}"
            embed = Embed(
                title=f"🔍 Word difficulty — {mode}{title_scope}",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            )
            embed.set_footer(text="Includes only words that appeared in ≥3 games.")
            return await ctx.send(embed=embed)

        if mode == "unseen":
            if lang_arg is None:
                return await ctx.send(
                    "❌ `unseen` requires a language: `$cwwords unseen es` or `en`."
                )
            rows = await self.bot.db.crossword_get_unseen_words(
                language=lang_arg, limit=limit,
            )
            if not rows:
                return await ctx.send(
                    "✅ Every word in the list has appeared at least once."
                )
            lines = [
                f"• `{r['word']}` ({r['difficulty']} · {r['theme']})"
                for r in rows
            ]
            embed = Embed(
                title=f"👀 Unseen words — {LANG_LABELS.get(lang_arg, lang_arg)}",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            )
            embed.set_footer(text="Words in the list that have never appeared in a game.")
            return await ctx.send(embed=embed)

        await ctx.send(
            "❌ Usage: `$cwwords <hardest|easiest|unseen> [lang] [limit]`"
        )

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
                quit_game = self._active.pop(channel_id, None)
                self._locks.pop(channel_id, None)
                watcher = self._watchers.pop(channel_id, None)
                if watcher and not watcher.done():
                    watcher.cancel()
                if quit_game is not None:
                    await self._persist_game_outcome(
                        quit_game,
                        truly_solved=set(quit_game.solvers.keys()),
                        completion="quit",
                    )
                try:
                    await self.bot.db.crossword_clear_active_game(channel_id)
                except Exception:
                    logger.debug(
                        "Failed to clear crossword active-game row on quit",
                        exc_info=True,
                    )
                await message.add_reaction("👋")
                await message.channel.send("🧩 Crossword cancelled.")
                return

        # Give up — owner-only, end game early but show answers (like timeout)
        if text.lower() in ("giveup", "give up", "reveal"):
            if message.author.id == game.starter_id:
                logger.info("Crossword give-up by %s in #%s", message.author, channel_id)
                await message.add_reaction("🏳️")
                await self._end_game(channel_id, completed=False)
            return

        # Hint — reveal one letter, max 2 per game
        if text.lower() == "!hint":
            word = game.use_hint()
            if word is None:
                await message.add_reaction("🚫")
            else:
                await message.add_reaction("💡")
                try:
                    if game.use_v2:
                        view, file = _build_v2_view(game)
                        msg = await message.channel.send(view=view, file=file)
                    else:
                        embed = game.build_embed()
                        img = game.render()
                        msg = await message.channel.send(embed=embed, file=img)
                    game.message = msg
                except discord.HTTPException:
                    pass
            return

        idx = game.try_solve(text)
        if idx is None:
            # Only react ❌ on single-word messages (likely intentional guesses)
            if " " not in text and len(text) <= 13:
                await message.add_reaction("❌")
            return

        # Correct answer!
        game.solved.add(idx)
        game.solvers[idx] = message.author.display_name
        game.solver_ids[idx] = message.author.id
        game.word_solved_at[idx] = time.monotonic() - game.started_at
        game.scores[message.author.id] = game.scores.get(message.author.id, 0) + 1
        game.scores_names[message.author.id] = message.author.display_name
        pw = game.grid.placed[idx]

        try:
            await self.bot.db.crossword_bump_solved(channel_id)
        except Exception:
            logger.debug("Failed to bump crossword solved_count", exc_info=True)

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
                    view, file = _build_v2_view(game)
                    msg = await message.channel.send(view=view, file=file)
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
        watcher = self._watchers.pop(channel_id, None)
        if watcher and not watcher.done() and watcher is not asyncio.current_task():
            watcher.cancel()
        if game is None:
            return

        outcome = "completed" if completed else "timeout"
        logger.info(
            "Crossword ended in #%s (%s, %d/%d solved, %.1fs)",
            channel_id, outcome, len(game.solved), len(game.grid.placed), game.elapsed,
        )

        # Capture the truly-solved set now, BEFORE the timeout branch
        # mutates game.solved to force-reveal unsolved words for display.
        truly_solved: set[int] = set(game.solvers.keys())

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

            channel = self.bot.get_channel(channel_id) or (game.message and game.message.channel)
            logger.info("DEBUG end-game COMPLETED: v2=%s ch_type=%s", game.use_v2, type(channel).__name__ if channel else "None")
            if channel:
                if game.use_v2:
                    view = discord.ui.LayoutView()
                    file = game.render()
                    view.add_item(discord.ui.Container(
                        discord.ui.TextDisplay(
                            f"## 🧩 Crossword Complete! 🎉\n"
                            f"Solved in **{minutes}m {seconds}s**\n\n{solver_text}"
                        ),
                        discord.ui.MediaGallery(
                            discord.MediaGalleryItem(media="attachment://crossword.png"),
                        ),
                        accent_colour=discord.Color.green(),
                    ))
                    await channel.send(view=view, file=file)
                else:
                    embed = Embed(
                        title="🧩 Crossword Complete! 🎉",
                        description=f"Solved in **{minutes}m {seconds}s**\n\n{solver_text}",
                        color=discord.Color.green(),
                    )
                    img = game.render()
                    embed.set_image(url="attachment://crossword.png")
                    await channel.send(embed=embed, file=img)
        else:
            for idx in range(len(game.grid.placed)):
                game.solved.add(idx)

            solved_count = len(game.solvers)
            total = len(game.grid.placed)

            channel = self.bot.get_channel(channel_id) or (game.message and game.message.channel)
            logger.info("DEBUG end-game TIMEOUT: v2=%s ch_type=%s", game.use_v2, type(channel).__name__ if channel else "None")
            if channel:
                # Always use embed for timeout — v2 LayoutView hangs from asyncio.Task
                embed = Embed(
                    title="🧩 Crossword — Time's Up! ⏱️",
                    description=game.build_clues_text(show_answers=True),
                    color=discord.Color.orange(),
                )
                img = game.render()
                embed.set_image(url="attachment://crossword.png")
                await channel.send(
                    f"⏱️ **Time's up!** {solved_count}/{total} words solved. Here are the answers:",
                    embed=embed, file=img,
                )

        # Persist normalized game outcome (games + participants + word events)
        await self._persist_game_outcome(
            game,
            truly_solved=truly_solved,
            completion="completed" if completed else "timeout",
        )

        # Clear the active-game row so we don't fire an interrupt notice
        # for a game that actually ended cleanly.
        try:
            await self.bot.db.crossword_clear_active_game(channel_id)
        except Exception:
            logger.debug(
                "Failed to clear crossword active-game row for #%s",
                channel_id, exc_info=True,
            )

    async def _persist_game_outcome(
        self, game: CrosswordGame, *, truly_solved: set[int], completion: str,
    ) -> None:
        """Write one game row + participant rows + word-event rows.

        Swallows exceptions so persistence failures never abort the user
        flow. Uses ``truly_solved`` (derived from ``game.solvers``) as the
        source of truth because the timeout branch of :meth:`_end_game`
        mutates ``game.solved`` for display purposes.
        """
        try:
            ended_at = datetime.now(UTC)

            participants: list[dict] = []
            per_user_solved: dict[int, int] = {}
            per_user_name: dict[int, str] = {}
            for widx in truly_solved:
                uid = game.solver_ids.get(widx)
                if uid is None:
                    continue
                per_user_solved[uid] = per_user_solved.get(uid, 0) + 1
                per_user_name[uid] = game.solvers.get(widx, str(uid))
            # Starter is always a participant even if they solved nothing.
            if game.starter_id and game.starter_id not in per_user_solved:
                per_user_solved[game.starter_id] = 0
                per_user_name.setdefault(game.starter_id, str(game.starter_id))
            for uid, count in per_user_solved.items():
                participants.append({
                    "user_id": uid,
                    "display_name": per_user_name.get(uid, str(uid)),
                    "words_solved": count,
                    "is_starter": uid == game.starter_id,
                })

            word_events: list[dict] = []
            for widx, _pw in enumerate(game.grid.placed):
                solved = widx in truly_solved
                word_events.append({
                    "word": game.get_answer(widx),
                    "solved": solved,
                    "solved_by": game.solver_ids.get(widx) if solved else None,
                    "seconds_to_solve": game.word_solved_at.get(widx) if solved else None,
                    "had_hint": widx in game.word_hints,
                })

            await self.bot.db.crossword_persist_game_outcome(
                game_id=game.game_id,
                guild_id=game.guild_id,
                channel_id=game.channel_id,
                starter_id=game.starter_id,
                difficulty=game.difficulty,
                language=game.language,
                total_words=len(game.grid.placed),
                words_solved=len(truly_solved),
                hints_used=game.hints_used,
                completion=completion,
                started_at=game.started_at_wall,
                ended_at=ended_at,
                elapsed_seconds=game.elapsed,
                participants=participants,
                word_events=word_events,
            )
        except Exception:
            logger.exception(
                "Failed to persist crossword outcome for game %s", game.game_id,
            )

    async def _timeout_watcher(self, channel_id: int) -> None:
        """End the game after the timeout period."""
        timeout = getattr(self, '_timeout_override', GAME_TIMEOUT_SECONDS)
        await asyncio.sleep(timeout)
        if channel_id in self._active:
            try:
                await self._end_game(channel_id, completed=False)
            except Exception:
                logger.exception("_timeout_watcher: _end_game raised for #%s", channel_id)
        else:
            logger.info("_timeout_watcher: game already ended for #%s", channel_id)

    async def cog_unload(self) -> None:
        """Clean up active games on cog unload."""
        if self._active:
            logger.warning(
                "Crossword cog unloading with %d active game(s): %s",
                len(self._active), list(self._active.keys()),
            )
        self._active.clear()
        self._locks.clear()
        for task in self._watchers.values():
            task.cancel()
        self._watchers.clear()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CrosswordCog(bot))
