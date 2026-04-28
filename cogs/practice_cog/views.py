"""Discord UI Views for practice sessions — Components V2 (LayoutView)."""
import random
from collections.abc import Awaitable, Callable

import discord
from discord import ButtonStyle, Color, Interaction, ui

from .modals import AnswerModal
from .session import PracticeCard, PracticeSession
from .srs import RATING_AGAIN, RATING_EASY, RATING_GOOD, RATING_HARD

LEVEL_LABELS = {"A": "Beginner", "B": "Intermediate", "C": "Advanced"}
LANG_EMOJI = {"spanish": "🇪🇸", "english": "🇬🇧"}


def _extract_blanked_word(card: PracticeCard) -> str | None:
    """Extract the actual word that was replaced by ___ in the sentence."""
    if "___" not in card.sentence_with_blank:
        return None
    parts = card.sentence_with_blank.split("___")
    if len(parts) != 2:
        return None
    prefix, suffix = parts
    result = card.sentence.removeprefix(prefix).removesuffix(suffix).strip()
    if not result or "___" in result:
        return None
    return result


def _normalize_word(text: str) -> str:
    """Lowercase strip for simple comparison."""
    return text.strip().lower()


# ── Question ──

def build_question_view(
    session: PracticeSession,
    card: PracticeCard,
    card_mode: str,
    distractors: list[str],
    on_answer: Callable[[Interaction, str], Awaitable[None]],
    on_skip: Callable[[Interaction], Awaitable[None]],
    on_quit: Callable[[Interaction], Awaitable[None]],
) -> ui.LayoutView:
    """Build a LayoutView for a practice question."""
    view = ui.LayoutView(timeout=300)

    level_label = LEVEL_LABELS.get(card.level, "")
    lang = LANG_EMOJI.get(session.language, "")
    footer = f"-# {lang} {session.language.title()}"
    if level_label:
        footer += f" · Level {card.level} ({level_label})"

    parts: list[ui.Item] = [
        ui.TextDisplay(f"## Practice ({session.progress_text})"),
        ui.TextDisplay(f"**{card.sentence_with_blank}**"),
    ]

    if session.show_hints and card.sentence_translation:
        parts.append(ui.Separator(visible=True))
        parts.append(ui.TextDisplay(f"-# *{card.sentence_translation}*"))

    # Choice or typing buttons
    if card_mode == "choice" and len(distractors) >= 3:
        # Use the actual blanked word (conjugated form) instead of the infinitive
        correct_label = _extract_blanked_word(card) or card.word
        # Deduplicate: remove distractors that match the correct answer
        unique_distractors = [d for d in distractors if _normalize_word(d) != _normalize_word(correct_label)]
        if len(unique_distractors) >= 3:
            choices = [*unique_distractors[:3], correct_label]
            random.shuffle(choices)
            choice_row = ui.ActionRow()
            for choice in choices:
                btn = ui.Button(label=choice[:80], style=ButtonStyle.primary)
                btn.callback = _answer_cb(on_answer, choice)
                choice_row.add_item(btn)
            parts.append(choice_row)
        else:
            # Not enough unique distractors — fall back to typing
            card_mode = "typing"

    if card_mode == "typing":
        type_row = ui.ActionRow()
        answer_btn = ui.Button(label="Answer", style=ButtonStyle.primary)
        answer_btn.callback = _modal_cb(card, on_answer)
        type_row.add_item(answer_btn)
        parts.append(type_row)

    # Control row
    ctrl = ui.ActionRow()
    skip_btn = ui.Button(label="Skip", style=ButtonStyle.secondary)
    skip_btn.callback = _simple_cb(on_skip)
    ctrl.add_item(skip_btn)
    quit_btn = ui.Button(label="Quit", style=ButtonStyle.danger)
    quit_btn.callback = _simple_cb(on_quit)
    ctrl.add_item(quit_btn)
    parts.append(ctrl)

    parts.append(ui.TextDisplay(footer))
    view.add_item(ui.Container(*parts, accent_colour=Color.blue()))
    return view


# ── Result ──

def build_result_view(
    card: PracticeCard,
    user_answer: str,
    was_correct: bool,
    *,
    tracked: bool,
    wrong_translation: str = "",
    on_rating: Callable[[Interaction, int], Awaitable[None]] | None = None,
    on_next: Callable[[Interaction], Awaitable[None]] | None = None,
    on_quit: Callable[[Interaction], Awaitable[None]] | None = None,
) -> ui.LayoutView:
    """Build a LayoutView for the answer result."""
    view = ui.LayoutView(timeout=300)
    actual_word = _extract_blanked_word(card) or card.word

    if was_correct:
        title = "## ✅ Correct!"
        colour = Color.green()
    else:
        title = "## ❌ Not quite"
        colour = Color.red()

    highlighted = card.sentence.replace(actual_word, f"**{actual_word}**")

    parts: list[ui.Item] = [ui.TextDisplay(title), ui.TextDisplay(highlighted)]

    if not was_correct:
        wrong_display = f"Your answer: ~~{user_answer[:100]}~~"
        if wrong_translation:
            wrong_display += f" ({wrong_translation})"
        parts.append(ui.TextDisplay(wrong_display))

    parts.append(ui.Separator(visible=True))
    # Show both the conjugated form and the dictionary form if they differ
    word_display = f"**{actual_word}** — {card.translation}"
    if _normalize_word(actual_word) != _normalize_word(card.word):
        word_display += f"  *(from {card.word})*"
    parts.append(ui.TextDisplay(word_display))

    if card.sentence_translation:
        parts.append(ui.TextDisplay(f"-# *{card.sentence_translation}*"))

    # Action row depends on tracked vs untracked
    row = ui.ActionRow()
    if tracked and on_rating:
        if was_correct:
            for label, style, rating in [
                ("Hard", ButtonStyle.secondary, RATING_HARD),
                ("Good", ButtonStyle.primary, RATING_GOOD),
                ("Easy", ButtonStyle.success, RATING_EASY),
            ]:
                btn = ui.Button(label=label, style=style)
                btn.callback = _rating_cb(on_rating, rating)
                row.add_item(btn)
        else:
            btn = ui.Button(label="Again", style=ButtonStyle.danger)
            btn.callback = _rating_cb(on_rating, RATING_AGAIN)
            row.add_item(btn)
    else:
        if on_next:
            next_btn = ui.Button(label="Next", style=ButtonStyle.primary)
            next_btn.callback = _simple_cb(on_next)
            row.add_item(next_btn)
        if on_quit:
            quit_btn = ui.Button(label="Quit", style=ButtonStyle.danger)
            quit_btn.callback = _simple_cb(on_quit)
            row.add_item(quit_btn)

    parts.append(row)
    view.add_item(ui.Container(*parts, accent_colour=colour))
    return view


# ── Summary ──

def build_summary_view(session: PracticeSession, *, quit_early: bool = False) -> ui.LayoutView:
    """Build a LayoutView for the session summary."""
    view = ui.LayoutView(timeout=None)

    if quit_early and session.total_reviewed == 0:
        view.add_item(ui.Container(
            ui.TextDisplay("## Session Ended"),
            ui.TextDisplay("No cards were reviewed."),
            accent_colour=Color.orange(),
        ))
        return view

    pct = (session.correct_count / session.total_reviewed * 100) if session.total_reviewed > 0 else 0
    title = "## Session Ended Early" if quit_early else "## 🎉 Session Complete!"

    view.add_item(ui.Container(
        ui.TextDisplay(title),
        ui.Separator(visible=True),
        ui.TextDisplay(
            f"**Score:** {session.correct_count}/{session.total_reviewed} ({pct:.0f}%)\n"
            f"**Cards reviewed:** {session.total_reviewed}"
        ),
        accent_colour=Color.gold(),
    ))
    return view


# ── Stats (still Embed — works outside ephemeral practice flow) ──

def create_stats_embed(language: str, stats: dict) -> discord.Embed:
    """Create an embed showing practice statistics with per-level breakdown."""
    lang_emoji = LANG_EMOJI.get(language, "")

    embed = discord.Embed(
        title=f"{lang_emoji} {language.title()} Practice Stats",
        color=Color.blue()
    )

    levels = stats.get('levels', {})
    for lvl in ("A", "B", "C"):
        lvl_stats = levels.get(lvl, {'due': 0, 'learning': 0, 'mastered': 0})
        name = f"Level {lvl} — {LEVEL_LABELS.get(lvl, '')}"
        value = f"📬 {lvl_stats['due']} due · 📖 {lvl_stats['learning']} learning · ✅ {lvl_stats['mastered']} mastered"
        embed.add_field(name=name, value=value, inline=False)

    embed.add_field(
        name="Overall",
        value=(
            f"**{stats['seen']}/{stats['total']}** cards seen · "
            f"**{stats['due']}** due now · "
            f"**{stats['mastered']}** mastered"
        ),
        inline=False,
    )
    return embed


# ── Callback helpers ──

def _answer_cb(on_answer, choice):
    async def cb(interaction: Interaction):
        await on_answer(interaction, choice)
    return cb


def _modal_cb(card, on_answer):
    async def cb(interaction: Interaction):
        modal = AnswerModal(card, on_answer)
        await interaction.response.send_modal(modal)
    return cb


def _simple_cb(fn):
    async def cb(interaction: Interaction):
        await fn(interaction)
    return cb


def _rating_cb(on_rating, rating):
    async def cb(interaction: Interaction):
        await on_rating(interaction, rating)
    return cb
