"""Views for the Introduce cog — multi-step selection UI."""
import logging

from discord import ButtonStyle, Embed, Interaction, SelectOption
from discord.ui import Button, Select, View, button

from .config import (
    COUNTRIES,
    EXCHANGE_COLOR,
    TIMEZONES,
)
from .modals import ExchangeDetailsModal, IntroOnlyModal, _lookup_display


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
                title="Introduction (Step 1/2)",
                description=(
                    "Great! Let's find you a language exchange partner.\n\n"
                    "Select your timezone, contact preference, and country below, "
                    "then click **Next** to fill in the details."
                ),
                color=EXCHANGE_COLOR,
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
    """Step 1/2: timezone, DM preference, country (Selects — too many options for RadioGroups)."""

    def __init__(self, introductions_channel_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.introductions_channel_id = introductions_channel_id

        self.timezone: str | None = None
        self.prefer_dm: bool = False
        self.country: str | None = None
        self.country_display: str | None = None

        self._build_selects()

    def _build_selects(self):
        tz = Select(
            placeholder="Select your timezone...",
            options=[SelectOption(label=lbl, value=v) for lbl, v in TIMEZONES],
            custom_id="timezone",
            row=0,
        )
        tz.callback = self._tz_cb
        self.add_item(tz)

        dm = Select(
            placeholder="Prefer DM contact?",
            options=[
                SelectOption(label="Yes", value="yes", description="Others should contact you via DM"),
                SelectOption(label="No", value="no", description="Others can mention you in the channel"),
            ],
            custom_id="prefer_dm",
            row=1,
        )
        dm.callback = self._dm_cb
        self.add_item(dm)

        country = Select(
            placeholder="Partner's country preference...",
            options=[SelectOption(label=lbl, value=v) for lbl, v in COUNTRIES],
            custom_id="country",
            row=2,
        )
        country.callback = self._country_cb
        self.add_item(country)

    async def _tz_cb(self, interaction: Interaction):
        self.timezone = interaction.data["values"][0]
        await interaction.response.defer()

    async def _dm_cb(self, interaction: Interaction):
        self.prefer_dm = interaction.data["values"][0] == "yes"
        await interaction.response.defer()

    async def _country_cb(self, interaction: Interaction):
        self.country = interaction.data["values"][0]
        self.country_display = _lookup_display(COUNTRIES, self.country)
        await interaction.response.defer()

    @button(label="Next: Language & Details →", style=ButtonStyle.primary, row=4)
    async def continue_button(self, interaction: Interaction, btn: Button):
        """Validate timezone and open the exchange details modal."""
        if not self.timezone:
            await interaction.response.send_message("Please select your timezone.", ephemeral=True)
            return

        await interaction.response.send_modal(
            ExchangeDetailsModal(parent_view=self, introductions_channel_id=self.introductions_channel_id),
        )

    async def on_timeout(self):
        logger.debug("ExchangePrefsView timed out")
