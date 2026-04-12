"""Views for the Introduce cog — multi-step selection UI."""
import logging

import discord
from discord import ButtonStyle, Embed, Interaction, SelectOption
from discord.ui import Button, Select, View, button

from .config import (
    OFFER_LANGUAGES,
    PROFICIENCY_LEVELS,
    REGIONS,
    SEEK_LANGUAGES,
)
from .modals import ExchangeDetailsModal, IntroOnlyModal

logger = logging.getLogger(__name__)


class IntroStartView(View):
    """Initial view: yes/no exchange partner question."""

    def __init__(self, introductions_channel_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.introductions_channel_id = introductions_channel_id
        self.seeking_exchange: bool | None = None

        select = Select(
            placeholder="Looking for an exchange partner?",
            options=[
                SelectOption(label="Yes", value="yes", description="I want to find a language exchange partner"),
                SelectOption(label="No", value="no", description="I just want to introduce myself"),
            ],
            custom_id="seeking_exchange",
            row=0,
        )
        select.callback = self._exchange_select_cb
        self.add_item(select)

    async def _exchange_select_cb(self, interaction: Interaction):
        self.seeking_exchange = interaction.data["values"][0] == "yes"
        await interaction.response.defer()

    @button(label="Continue →", style=ButtonStyle.primary, row=1)
    async def continue_button(self, interaction: Interaction, btn: Button):
        """Branch based on selection."""
        if self.seeking_exchange is None:
            await interaction.response.send_message(
                "Please select whether you're looking for an exchange partner.",
                ephemeral=True,
            )
            return

        if self.seeking_exchange:
            view = ExchangePrefsView(introductions_channel_id=self.introductions_channel_id)
            embed = Embed(
                title="Find an Exchange Partner",
                description="Fill in your details below, then click **Next** to finish.",
                color=discord.Color.teal(),
            )
            embed.set_footer(text="This form will expire in 5 minutes")
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_modal(
                IntroOnlyModal(introductions_channel_id=self.introductions_channel_id),
            )

    async def on_timeout(self):
        logger.debug("IntroStartView timed out")


class ExchangePrefsView(View):
    """Selects for language offer/seek, level, region, DM pref — then modal for free text."""

    def __init__(self, introductions_channel_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.introductions_channel_id = introductions_channel_id

        self.offer_lang: str | None = None
        self.seek_lang: str | None = None
        self.seek_level: str | None = None
        self.region: str | None = None
        self.prefer_dm: bool = True

        self._build_selects()

    def _build_selects(self):
        offer = Select(
            placeholder="Language you speak natively...",
            options=[SelectOption(label=lbl, value=v) for lbl, v in OFFER_LANGUAGES],
            custom_id="offer_lang",
            row=0,
        )
        offer.callback = self._offer_cb
        self.add_item(offer)

        seek = Select(
            placeholder="Language you want to learn...",
            options=[SelectOption(label=lbl, value=v) for lbl, v in SEEK_LANGUAGES],
            custom_id="seek_lang",
            row=1,
        )
        seek.callback = self._seek_cb
        self.add_item(seek)

        level = Select(
            placeholder="Your level in that language...",
            options=[SelectOption(label=lbl, value=v) for lbl, v in PROFICIENCY_LEVELS],
            custom_id="seek_level",
            row=2,
        )
        level.callback = self._level_cb
        self.add_item(level)

        region = Select(
            placeholder="Your region...",
            options=[SelectOption(label=lbl, value=v) for lbl, v in REGIONS],
            custom_id="region",
            row=3,
        )
        region.callback = self._region_cb
        self.add_item(region)

    async def _offer_cb(self, interaction: Interaction):
        self.offer_lang = interaction.data["values"][0]
        await interaction.response.defer()

    async def _seek_cb(self, interaction: Interaction):
        self.seek_lang = interaction.data["values"][0]
        await interaction.response.defer()

    async def _level_cb(self, interaction: Interaction):
        self.seek_level = interaction.data["values"][0]
        await interaction.response.defer()

    async def _region_cb(self, interaction: Interaction):
        self.region = interaction.data["values"][0]
        await interaction.response.defer()

    @button(label="Next: About You →", style=ButtonStyle.primary, row=4)
    async def continue_button(self, interaction: Interaction, btn: Button):
        """Validate selections and open the details modal."""
        missing = []
        if not self.offer_lang:
            missing.append("language you speak")
        if not self.seek_lang:
            missing.append("language you want to learn")
        if not self.seek_level:
            missing.append("your level")
        if not self.region:
            missing.append("your region")

        if missing:
            await interaction.response.send_message(
                f"Please select: {', '.join(missing)}.", ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            ExchangeDetailsModal(
                parent_view=self,
                introductions_channel_id=self.introductions_channel_id,
            ),
        )

    async def on_timeout(self):
        logger.debug("ExchangePrefsView timed out")
