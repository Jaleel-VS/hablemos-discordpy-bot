"""Shared catalogs and Components V2 study browser for advanced English and Spanish."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import discord
from discord import app_commands, ui

from base_cog import BaseCog

if TYPE_CHECKING:
    from hablemos import Hablemos

logger = logging.getLogger(__name__)
type VocabularyLanguage = Literal["es", "en"]

REGISTERS = frozenset({"neutro", "coloquial", "formal", "literario"})
_FIELD_LIMITS = {
    "id": 80,
    "term": 60,
    "meaning_es": 220,
    "meaning_en": 220,
    "register": 20,
    "region": 50,
    "collocation": 100,
    "note": 180,
}
_ACCENTS = {
    "neutro": discord.Color.teal(),
    "coloquial": discord.Color.gold(),
    "formal": discord.Color.blurple(),
    "literario": discord.Color.purple(),
}
_ENGLISH_REGISTERS = {
    "neutro": "Neutral", "coloquial": "Informal", "formal": "Formal", "literario": "Literary",
}
_REFERENCE_URLS = {
    "es": (
        "https://cvc.cervantes.es/ensenanza/biblioteca_ele/plan_curricular/"
        "niveles/08_nociones_generales_inventario_c1-c2.htm"
    ),
    "en": "https://www.oxfordlearnersdictionaries.com/",
}
_COMMANDS = {"es": "c", "en": "e"}


@dataclass(frozen=True, slots=True)
class Example:
    """An original usage example expressed in Spanish and English."""

    es: str
    en: str


@dataclass(frozen=True, slots=True)
class VocabularyEntry:
    """One sense of an advanced word or expression, with usage guidance."""

    id: str
    term: str
    meaning_es: str
    meaning_en: str
    register: str
    region: str
    collocation: str
    note: str
    examples: tuple[Example, ...]


def normalize(text: str) -> str:
    """Normalize accents, case, and spacing for forgiving term searches."""
    return " ".join(
        "".join(
            char for char in unicodedata.normalize("NFD", text.casefold())
            if not unicodedata.combining(char)
        ).split()
    )


def _text(value: object, limit: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"Invalid vocabulary field: {label}")
    return value.strip()


def load_catalog(directory: Path) -> tuple[VocabularyEntry, ...]:
    """Load every data slice, rejecting duplicate terms and malformed cards."""
    entries: list[VocabularyEntry] = []
    ids: set[str] = set()
    terms: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError(f"Vocabulary data must be an array: {path.name}")
        for row in rows:
            if not isinstance(row, dict) or set(row) != {*_FIELD_LIMITS, "examples"}:
                raise ValueError(f"Unexpected vocabulary fields in {path.name}")
            fields = {key: _text(row[key], limit, key) for key, limit in _FIELD_LIMITS.items()}
            if fields["register"] not in REGISTERS:
                raise ValueError(f"Unknown vocabulary register: {fields['register']}")
            raw_examples = row["examples"]
            if not isinstance(raw_examples, list) or len(raw_examples) != 2:
                raise ValueError(f"Expected two examples for {fields['term']}")
            examples: list[Example] = []
            for example in raw_examples:
                if not isinstance(example, dict) or set(example) != {"es", "en"}:
                    raise ValueError(f"Invalid example for {fields['term']}")
                examples.append(Example(
                    es=_text(example["es"], 220, "example.es"),
                    en=_text(example["en"], 220, "example.en"),
                ))
            term_key = normalize(fields["term"])
            if fields["id"] in ids or term_key in terms:
                raise ValueError(f"Duplicate vocabulary entry: {fields['term']}")
            ids.add(fields["id"])
            terms.add(term_key)
            entries.append(VocabularyEntry(**fields, examples=tuple(examples)))
    if not entries:
        raise ValueError("The vocabulary catalog is empty")
    return tuple(sorted(entries, key=lambda entry: normalize(entry.term)))


def find_entries(entries: tuple[VocabularyEntry, ...], query: str) -> tuple[VocabularyEntry, ...]:
    """Find an exact term first, otherwise match a fragment of its headword."""
    key = normalize(query)
    if not key:
        return entries
    matches: list[VocabularyEntry] = []
    for entry in entries:
        term = normalize(entry.term)
        if term == key:
            return (entry,)
        if key in term:
            matches.append(entry)
    return tuple(matches)


class VocabularyView(ui.LayoutView):
    """Browse a fixed deck; only its invoker can navigate or toggle translations."""

    def __init__(
        self, entries: tuple[VocabularyEntry, ...], invoker_id: int,
        *, language: VocabularyLanguage,
    ) -> None:
        if not entries:
            raise ValueError("A vocabulary browser needs at least one entry")
        super().__init__(timeout=600)
        self.entries = entries
        self.invoker_id = invoker_id
        self.language = language
        self.command_hint = f"/{_COMMANDS[language]}"
        self.index = 0
        self.show_translation = True
        self.expired = False
        self.message: discord.Message | None = None
        self._lock = asyncio.Lock()
        self._rebuild()

    def _rebuild(self) -> None:
        entry = self.entries[self.index]
        english = self.language == "en"
        escape = discord.utils.escape_markdown
        region = ("General usage" if english else "Uso general") if entry.region == "general" else entry.region
        register = _ENGLISH_REGISTERS[entry.register] if english else entry.register.capitalize()
        heading = "LEXICON · ADVANCED ENGLISH" if english else "LÉXICO · ESPAÑOL AVANZADO"
        primary = entry.meaning_en if english else entry.meaning_es
        translation = entry.meaning_es if english else entry.meaning_en
        meaning = f"### {'Meaning' if english else 'Qué significa'}\n{escape(primary)}"
        if self.show_translation:
            meaning += f"\n*{escape(translation)}*"
        examples = ["### In context" if english else "### En contexto"]
        for number, example in enumerate(entry.examples, start=1):
            primary = example.en if english else example.es
            translation = example.es if english else example.en
            examples.append(f"**{number:02d}** {escape(primary)}")
            if self.show_translation:
                examples.append(f"-# {escape(translation)}")
        previous = ui.Button(
            label="Previous" if english else "Anterior", style=discord.ButtonStyle.secondary,
            disabled=self.expired or self.index == 0,
        )
        previous.callback = self._previous
        next_button = ui.Button(
            label="Next" if english else "Siguiente", style=discord.ButtonStyle.primary,
            disabled=self.expired or self.index == len(self.entries) - 1,
        )
        next_button.callback = self._next
        if english:
            toggle_label = "Hide Spanish" if self.show_translation else "Show Spanish"
            status = "Session ended" if self.expired else "10 min inactivity timeout"
        else:
            toggle_label = "Ocultar inglés" if self.show_translation else "Mostrar inglés"
            status = "Sesión finalizada" if self.expired else "10 min de inactividad"
        toggle = ui.Button(label=toggle_label, disabled=self.expired)
        toggle.callback = self._toggle_translation
        self.clear_items()
        self.add_item(ui.Container(
            ui.TextDisplay(f"-# {heading}\n## {escape(entry.term)}\n-# {register} · {escape(region)}"),
            ui.TextDisplay(meaning),
            ui.Separator(),
            ui.TextDisplay("\n\n".join(examples)),
            ui.Separator(),
            ui.TextDisplay(
                f"**{'Common collocation' if english else 'Combinación natural'}**\n{escape(entry.collocation)}\n\n"
                f"**{'Usage note' if english else 'Matiz de uso'}**\n{escape(entry.note)}"
            ),
            ui.TextDisplay(
                f"-# {self.index + 1} / {len(self.entries)} · "
                f"{'Original examples' if english else 'Ejemplos originales'} · {status}"
            ),
            ui.ActionRow(
                previous, next_button, toggle,
                ui.Button(
                    label="Oxford Learner's" if english else "Inventario Cervantes",
                    style=discord.ButtonStyle.link, url=_REFERENCE_URLS[self.language],
                ),
            ),
            accent_colour=_ACCENTS[entry.register],
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Keep other readers from changing the invoker's study card."""
        if interaction.user.id != self.invoker_id:
            text = (
                f"This card belongs to another reader. Use `{self.command_hint}` to open your own."
                if self.language == "en" else
                f"Esta tarjeta tiene otro lector. Usa `{self.command_hint}` para abrir la tuya."
            )
            await interaction.response.send_message(
                text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            )
            return False
        return True

    async def _change(self, interaction: discord.Interaction, *, step: int = 0, toggle: bool = False) -> None:
        await interaction.response.defer()
        async with self._lock:
            if self.expired:
                return
            previous_index, previous_translation = self.index, self.show_translation
            self.index = max(0, min(len(self.entries) - 1, self.index + step))
            if toggle:
                self.show_translation = not self.show_translation
            self._rebuild()
            try:
                await interaction.edit_original_response(view=self, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                self.index, self.show_translation = previous_index, previous_translation
                self._rebuild()
                raise

    async def _previous(self, interaction: discord.Interaction) -> None:
        await self._change(interaction, step=-1)

    async def _next(self, interaction: discord.Interaction) -> None:
        await self._change(interaction, step=1)

    async def _toggle_translation(self, interaction: discord.Interaction) -> None:
        await self._change(interaction, toggle=True)

    async def on_timeout(self) -> None:
        """Leave the last card readable and disable its expired study controls."""
        async with self._lock:
            self.expired = True
            self._rebuild()
            if self.message is None:
                return
            try:
                await self.message.edit(view=self, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                logger.exception("Unable to expire an advanced vocabulary card")

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
        """Log interaction failures without exposing exception details to readers."""
        logger.error("Advanced vocabulary interaction failed", exc_info=(type(error), error, error.__traceback__))
        try:
            text = "No se pudo actualizar la tarjeta. Vuelve a intentarlo. / Could not update the card. Please try again."
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            else:
                await interaction.response.send_message(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.exception("Unable to send the vocabulary interaction error response")


class VocabularyCog(BaseCog):
    """Common catalog loading and command behavior for each native-language deck."""

    def __init__(self, bot: Hablemos, directory: Path, language: VocabularyLanguage) -> None:
        super().__init__(bot)
        self.entries = load_catalog(directory)
        self.language = language

    async def show_card(self, interaction: discord.Interaction, query: str) -> None:
        """Send an exact-match, search-results, or shuffled vocabulary browser."""
        matches = find_entries(self.entries, query)
        try:
            if not matches:
                hint = f"/{_COMMANDS[self.language]}"
                message = (
                    f"No matching term found. Try another word or use `{hint}` without arguments."
                    if self.language == "en" else
                    f"No encontré ese término. Prueba otra palabra o usa `{hint}` sin argumentos."
                )
                await interaction.response.send_message(
                    message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
                )
                return
            if not query.strip():
                deck = list(matches)
                random.shuffle(deck)
                matches = tuple(deck)
            view = VocabularyView(matches, interaction.user.id, language=self.language)
            await interaction.response.send_message(
                view=view, ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
            )
            view.message = await interaction.original_response()
        except discord.HTTPException:
            logger.exception("Unable to send an advanced vocabulary card")

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError,
    ) -> None:
        """Answer slash-command failures without exposing exception details."""
        if isinstance(error, app_commands.CommandOnCooldown):
            message = (
                f"Try again in {error.retry_after:.1f} seconds."
                if self.language == "en" else
                f"Vuelve a intentarlo en {error.retry_after:.1f} segundos."
            )
        else:
            logger.error("Advanced vocabulary command failed", exc_info=(type(error), error, error.__traceback__))
            message = (
                "Could not open the card. Please try again."
                if self.language == "en" else
                "No se pudo abrir la tarjeta. Vuelve a intentarlo."
            )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            else:
                await interaction.response.send_message(
                    message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
                )
        except discord.HTTPException:
            logger.exception("Unable to send the vocabulary command error response")
