"""
Conjugation practice cog — interactive Spanish verb conjugation game.

Uses Components V2 (LayoutView) for ephemeral, button-driven sessions.
Verb data stored in PostgreSQL (conjugation_verbs + conjugation_forms).
"""
from __future__ import annotations

import logging
import random
import time

import discord
from discord import Interaction, app_commands
from discord.ext import commands

from base_cog import BaseCog

from .session import ConjugationCard, ConjugationMode, ConjugationSession
from .views import build_question_view, build_result_view, build_summary_view

logger = logging.getLogger(__name__)

TENSES = [
    ("presente", "Present"),
    ("pretérito", "Preterite"),
    ("imperfecto", "Imperfect"),
    ("futuro", "Future"),
    ("condicional", "Conditional"),
    ("pretérito_perfecto", "Present Perfect"),
    ("pluscuamperfecto", "Pluperfect"),
    ("subjuntivo_presente", "Subj. Present"),
    ("subjuntivo_imperfecto", "Subj. Imperfect"),
    ("imperativo_afirmativo", "Imperative (+)"),
    ("imperativo_negativo", "Imperative (−)"),
]


def _normalize(text: str) -> str:
    return text.strip().lower()


_PRONOUNS = {"yo", "tú", "tu", "él", "el", "ella", "nosotros", "nosotras",
             "vosotros", "vosotras", "ellos", "ellas", "usted", "ustedes"}


def _strip_pronoun(text: str) -> str:
    """Strip a leading pronoun if the user typed 'yo hablo' instead of 'hablo'."""
    parts = text.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() in _PRONOUNS:
        return parts[1]
    return text


class ConjugationCog(BaseCog):
    """Interactive Spanish verb conjugation practice."""

    SESSION_TTL = 1800
    MAX_SESSIONS = 50

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.active_sessions: dict[int, ConjugationSession] = {}

    def _purge_stale(self) -> None:
        now = time.time()
        stale = [uid for uid, s in self.active_sessions.items()
                 if now - s.created_at > self.SESSION_TTL]
        for uid in stale:
            del self.active_sessions[uid]

    # ── DB queries ──

    async def _get_cards(
        self, category: str | None, tense: str | None, limit: int,
    ) -> list[ConjugationCard]:
        """Get random conjugation questions from the DB."""
        conditions = []
        args: list = []
        idx = 1

        if category:
            conditions.append(f"v.category = ${idx}")
            args.append(category)
            idx += 1
        if tense:
            conditions.append(f"f.tense = ${idx}")
            args.append(tense)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        rows = await self.bot.db._fetch(f"""
            SELECT v.id, v.infinitive, v.english, f.tense, f.pronoun, f.form
            FROM conjugation_forms f
            JOIN conjugation_verbs v ON v.id = f.verb_id
            {where}
            ORDER BY random()
            LIMIT ${idx}
        """, *args, limit)

        return [
            ConjugationCard(
                verb_id=r["id"], infinitive=r["infinitive"], english=r["english"],
                tense=r["tense"], pronoun=r["pronoun"], correct_form=r["form"],
            )
            for r in rows
        ]

    async def _get_distractors(
        self, tense: str, pronoun: str, correct_form: str, verb_id: int,
    ) -> list[str]:
        """Get 3 plausible wrong answers (same verb+tense, different pronoun)."""
        rows = await self.bot.db._fetch("""
            SELECT f.form FROM conjugation_forms f
            WHERE f.tense = $1 AND f.verb_id = $2
              AND f.pronoun != $3 AND f.form != $4
            ORDER BY random() LIMIT 3
        """, tense, verb_id, pronoun, correct_form)
        return [r["form"] for r in rows]

    async def _get_categories(self) -> list[dict]:
        """Get categories with verb counts."""
        return await self.bot.db._fetch("""
            SELECT category, count(*) as verb_count
            FROM conjugation_verbs
            WHERE category IS NOT NULL
            GROUP BY category ORDER BY verb_count DESC
        """)

    # ── Slash commands ──

    conj_group = app_commands.Group(
        name="conjugate", description="Spanish verb conjugation practice",
    )

    @conj_group.command(name="start", description="Start a conjugation practice session")
    @app_commands.describe(
        category="Verb category",
        tense="Tense to practice (or 'all')",
        mode="Multiple choice or typing",
        count="Number of questions (5–20)",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="High Frequency", value="high-frequency"),
            app_commands.Choice(name="Regular -AR", value="regular-ar"),
            app_commands.Choice(name="Regular -ER", value="regular-er"),
            app_commands.Choice(name="Regular -IR", value="regular-ir"),
            app_commands.Choice(name="All Categories", value="all"),
        ],
        tense=[
            app_commands.Choice(name="All Tenses", value="all"),
            *[app_commands.Choice(name=display, value=key) for key, display in TENSES],
        ],
        mode=[
            app_commands.Choice(name="Multiple choice", value="choice"),
            app_commands.Choice(name="Typing", value="typing"),
        ],
        count=[
            app_commands.Choice(name="5", value=5),
            app_commands.Choice(name="10", value=10),
            app_commands.Choice(name="15", value=15),
            app_commands.Choice(name="20", value=20),
        ],
    )
    async def conj_start(
        self, interaction: Interaction,
        category: str = "high-frequency", tense: str = "all",
        mode: str = "choice", count: int = 10,
    ):
        user_id = interaction.user.id
        self._purge_stale()

        if user_id in self.active_sessions:
            await interaction.response.send_message(
                "You already have an active session. Finish or quit it first.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        cat_filter = None if category == "all" else category
        tense_filter = None if tense == "all" else tense

        cards = await self._get_cards(cat_filter, tense_filter, count)
        if not cards:
            await interaction.followup.send(
                "No conjugation data found for that combination.", ephemeral=True,
            )
            return

        session = ConjugationSession(
            user_id=user_id, mode=ConjugationMode(mode), cards=cards,
        )
        self.active_sessions[user_id] = session
        await self._show_question(interaction, session, is_first=True)

    @conj_group.command(name="categories", description="Show available verb categories")
    async def conj_categories(self, interaction: Interaction):
        cats = await self._get_categories()
        lines = [f"`{c['category']}` — {c['verb_count']} verbs" for c in cats]
        embed = discord.Embed(
            title="Conjugation Categories",
            description="\n".join(lines) if lines else "No categories found.",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Session flow ──

    async def _show_question(
        self, interaction: Interaction, session: ConjugationSession, *, is_first: bool = False,
    ):
        card = session.current_card
        if card is None or session.is_complete:
            await self._end_session(interaction, session)
            return

        card_mode = session.mode.value
        distractors: list[str] = []

        if card_mode == "choice":
            distractors = await self._get_distractors(
                card.tense, card.pronoun, card.correct_form, card.verb_id,
            )
            if len(distractors) < 3:
                card_mode = "typing"

        view = build_question_view(
            session=session, card=card, card_mode=card_mode, distractors=distractors,
            on_answer=lambda i, a: self._handle_answer(i, session, a),
            on_skip=lambda i: self._handle_skip(i, session),
            on_quit=lambda i: self._handle_quit(i, session),
        )

        if is_first:
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            try:
                await interaction.response.edit_message(view=view)
            except discord.InteractionResponded:
                await interaction.followup.send(view=view, ephemeral=True)

    async def _handle_answer(
        self, interaction: Interaction, session: ConjugationSession, user_answer: str,
    ):
        card = session.current_card
        if card is None:
            return

        was_correct = _normalize(user_answer) == _normalize(card.correct_form)
        if not was_correct:
            was_correct = _normalize(_strip_pronoun(user_answer)) == _normalize(card.correct_form)
        session.record_answer(was_correct)
        session.advance()

        view = build_result_view(
            card, user_answer, was_correct,
            on_next=lambda i: self._show_question(i, session)
            if not session.is_complete else self._end_session(i, session),
            on_quit=lambda i: self._handle_quit(i, session),
        )

        try:
            await interaction.response.edit_message(view=view)
        except discord.InteractionResponded:
            await interaction.followup.send(view=view, ephemeral=True)

    async def _handle_skip(self, interaction: Interaction, session: ConjugationSession):
        session.advance()
        if session.is_complete:
            await self._end_session(interaction, session)
        else:
            await self._show_question(interaction, session)

    async def _handle_quit(self, interaction: Interaction, session: ConjugationSession):
        await self._end_session(interaction, session, quit_early=True)

    async def _end_session(
        self, interaction: Interaction, session: ConjugationSession, quit_early: bool = False,
    ):
        self.active_sessions.pop(session.user_id, None)
        view = build_summary_view(session, quit_early=quit_early)
        try:
            await interaction.response.edit_message(view=view)
        except discord.InteractionResponded:
            await interaction.followup.send(view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ConjugationCog(bot))
    logger.info("ConjugationCog loaded")
