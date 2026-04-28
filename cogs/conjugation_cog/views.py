"""Discord UI Views for conjugation sessions — Components V2 (LayoutView)."""
import random
from collections.abc import Awaitable, Callable

from discord import ButtonStyle, Color, Interaction, ui

from .modals import ConjugationAnswerModal
from .session import ConjugationCard, ConjugationSession

TENSE_DISPLAY = {
    "presente": "Present",
    "pretérito": "Preterite",
    "imperfecto": "Imperfect",
    "futuro": "Future",
    "condicional": "Conditional",
    "pretérito_perfecto": "Present Perfect",
    "pluscuamperfecto": "Pluperfect",
    "subjuntivo_presente": "Subj. Present",
    "subjuntivo_imperfecto": "Subj. Imperfect",
    "imperativo_afirmativo": "Imperative (+)",
    "imperativo_negativo": "Imperative (−)",
}

PRONOUN_DISPLAY = {
    "yo": "yo",
    "tú": "tú",
    "él/ella": "él",
    "nosotros": "nosotros",
    "vosotros": "vosotros",
    "ellos/ellas": "ellos",
}


# ── Question ──

def build_question_view(
    session: ConjugationSession,
    card: ConjugationCard,
    card_mode: str,
    distractors: list[str],
    on_answer: Callable[[Interaction, str], Awaitable[None]],
    on_skip: Callable[[Interaction], Awaitable[None]],
    on_quit: Callable[[Interaction], Awaitable[None]],
) -> ui.LayoutView:
    view = ui.LayoutView(timeout=300)

    pronoun = PRONOUN_DISPLAY.get(card.pronoun, card.pronoun)
    tense = TENSE_DISPLAY.get(card.tense, card.tense)

    parts: list[ui.Item] = [
        ui.TextDisplay(f"## Conjugation ({session.progress_text})"),
        ui.TextDisplay(f"# {pronoun} + {card.infinitive}\n*{card.english}*"),
        ui.TextDisplay(f"-# Tense: **{tense}**"),
    ]

    if card_mode == "choice" and len(distractors) >= 3:
        choices = [*distractors[:3], card.correct_form]
        random.shuffle(choices)
        row = ui.ActionRow()
        for choice in choices:
            btn = ui.Button(label=choice[:80], style=ButtonStyle.primary)
            btn.callback = _answer_cb(on_answer, choice)
            row.add_item(btn)
        parts.append(row)
    else:
        row = ui.ActionRow()
        btn = ui.Button(label="Answer", style=ButtonStyle.primary)
        btn.callback = _modal_cb(on_answer)
        row.add_item(btn)
        parts.append(row)

    ctrl = ui.ActionRow()
    skip_btn = ui.Button(label="Skip", style=ButtonStyle.secondary)
    skip_btn.callback = _simple_cb(on_skip)
    ctrl.add_item(skip_btn)
    quit_btn = ui.Button(label="Quit", style=ButtonStyle.danger)
    quit_btn.callback = _simple_cb(on_quit)
    ctrl.add_item(quit_btn)
    parts.append(ctrl)

    view.add_item(ui.Container(*parts, accent_colour=Color.blue()))
    return view


# ── Result ──

def build_result_view(
    card: ConjugationCard,
    user_answer: str,
    was_correct: bool,
    on_next: Callable[[Interaction], Awaitable[None]],
    on_quit: Callable[[Interaction], Awaitable[None]],
) -> ui.LayoutView:
    view = ui.LayoutView(timeout=300)

    pronoun = PRONOUN_DISPLAY.get(card.pronoun, card.pronoun)

    if was_correct:
        title = "## ✅ Correct!"
        colour = Color.green()
    else:
        title = "## ❌ Not quite"
        colour = Color.red()

    parts: list[ui.Item] = [
        ui.TextDisplay(title),
        ui.TextDisplay(f"**{pronoun} {card.correct_form}**"),
    ]

    if not was_correct:
        parts.append(ui.TextDisplay(f"Your answer: ~~{user_answer[:100]}~~"))

    parts.append(ui.Separator(visible=True))
    parts.append(ui.TextDisplay(
        f"**{card.infinitive}** — {card.english}"
    ))

    row = ui.ActionRow()
    next_btn = ui.Button(label="Next", style=ButtonStyle.primary)
    next_btn.callback = _simple_cb(on_next)
    row.add_item(next_btn)
    quit_btn = ui.Button(label="Quit", style=ButtonStyle.danger)
    quit_btn.callback = _simple_cb(on_quit)
    row.add_item(quit_btn)
    parts.append(row)

    view.add_item(ui.Container(*parts, accent_colour=colour))
    return view


# ── Summary ──

def build_summary_view(session: ConjugationSession, *, quit_early: bool = False) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)

    if quit_early and session.total_reviewed == 0:
        view.add_item(ui.Container(
            ui.TextDisplay("## Session Ended"),
            ui.TextDisplay("No questions answered."),
            accent_colour=Color.orange(),
        ))
        return view

    if session.total_reviewed == 0:
        view.add_item(ui.Container(
            ui.TextDisplay("## Session Complete"),
            ui.TextDisplay("All questions skipped."),
            accent_colour=Color.orange(),
        ))
        return view

    pct = (session.correct_count / session.total_reviewed * 100) if session.total_reviewed else 0
    title = "## Session Ended Early" if quit_early else "## 🎉 Session Complete!"

    if pct == 100:
        comment = "Perfecto!"
    elif pct >= 80:
        comment = "Excelente!"
    elif pct >= 60:
        comment = "Bien hecho!"
    else:
        comment = "Sigue practicando!"

    view.add_item(ui.Container(
        ui.TextDisplay(title),
        ui.Separator(visible=True),
        ui.TextDisplay(
            f"**Score:** {session.correct_count}/{session.total_reviewed} ({pct:.0f}%)\n"
            f"**{comment}**"
        ),
        accent_colour=Color.gold(),
    ))
    return view


# ── Callback helpers ──

def _answer_cb(on_answer, choice):
    async def cb(interaction: Interaction):
        await on_answer(interaction, choice)
    return cb


def _modal_cb(on_answer):
    async def cb(interaction: Interaction):
        await interaction.response.send_modal(ConjugationAnswerModal(on_answer))
    return cb


def _simple_cb(fn):
    async def cb(interaction: Interaction):
        await fn(interaction)
    return cb
