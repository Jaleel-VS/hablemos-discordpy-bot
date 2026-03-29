"""Views for the Introduce cog — multi-step selection UI."""
import logging

from discord import ButtonStyle, Embed, Interaction, SelectOption
from discord.ui import Button, Select, View, button

from .config import (
    COUNTRIES,
    EXCHANGE_COLOR,
    LANGUAGES,
    PROFICIENCY_LEVELS,
    TIMEZONES,
)
from .modals import ExchangeDetailsModal, IntroOnlyModal

logger = logging.getLogger(__name__)


def _lookup_display(options: list[tuple[str, str]], value: str) -> str:
    """Return the display label for a value from a (label, value) option list."""
    return next((label for label, v in options if v == value), value)


class IntroStartView(View):
    """Initial view asking if user wants to find an exchange partner."""

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
        select.callback = self._exchange_select_callback
        self.add_item(select)

    async def _exchange_select_callback(self, interaction: Interaction):
        self.seeking_exchange = interaction.data["values"][0] == "yes"
        await interaction.response.defer()

    @button(label="Continue →", style=ButtonStyle.primary, row=1)
    async def continue_button(self, interaction: Interaction, btn: Button):
        """Branch to appropriate flow based on selection."""
        if self.seeking_exchange is None:
            await interaction.response.send_message(
                "Please select whether you're looking for an exchange partner.",
                ephemeral=True,
            )
            return

        if self.seeking_exchange:
            view = ExchangeRequestView(introductions_channel_id=self.introductions_channel_id)
            embed = Embed(
                title="Introduction (Step 2/4)",
                description=(
                    "Great! Let's find you a language exchange partner.\n\n"
                    "**Step 2:** Select the languages you offer and are looking for."
                ),
                color=EXCHANGE_COLOR,
            )
            embed.set_footer(text="This form will expire in 5 minutes")
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            modal = IntroOnlyModal(introductions_channel_id=self.introductions_channel_id)
            await interaction.response.send_modal(modal)

    async def on_timeout(self):
        logger.debug("IntroStartView timed out")


class ExchangeRequestView(View):
    """Step 2/4: language and proficiency selection."""

    def __init__(self, introductions_channel_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.introductions_channel_id = introductions_channel_id

        # Selection state
        self.language_offering: str | None = None
        self.offering_level: str | None = None
        self.language_seeking: str | None = None
        self.seeking_level: str | None = None
        self.timezone: str | None = None
        self.prefer_dm: bool = False
        self.country: str | None = None

        # Display labels
        self.language_offering_display: str | None = None
        self.offering_level_display: str | None = None
        self.language_seeking_display: str | None = None
        self.seeking_level_display: str | None = None
        self.country_display: str | None = None

        self._build_selects()

    def _add_select(
        self, options_list: list[tuple[str, str]], placeholder: str, custom_id: str, row: int,
    ) -> Select:
        """Create a Select from a (label, value) list and add it to the view."""
        select = Select(
            placeholder=placeholder,
            options=[SelectOption(label=lbl, value=v) for lbl, v in options_list],
            custom_id=custom_id,
            row=row,
        )
        self.add_item(select)
        return select

    def _build_selects(self):
        """Build all select menus for step 2."""
        s = self._add_select(LANGUAGES, "Language you offer...", "lang_offer", 0)
        s.callback = self._lang_offer_cb

        s = self._add_select(PROFICIENCY_LEVELS, "Your level in that language...", "offer_level", 1)
        s.callback = self._offer_level_cb

        s = self._add_select(LANGUAGES, "Language you're looking for...", "lang_seek", 2)
        s.callback = self._lang_seek_cb

        s = self._add_select(PROFICIENCY_LEVELS, "Partner's minimum level...", "seek_level", 3)
        s.callback = self._seek_level_cb

    async def _lang_offer_cb(self, interaction: Interaction):
        self.language_offering = interaction.data["values"][0]
        self.language_offering_display = _lookup_display(LANGUAGES, self.language_offering)
        await interaction.response.defer()

    async def _offer_level_cb(self, interaction: Interaction):
        self.offering_level = interaction.data["values"][0]
        self.offering_level_display = _lookup_display(PROFICIENCY_LEVELS, self.offering_level)
        await interaction.response.defer()

    async def _lang_seek_cb(self, interaction: Interaction):
        self.language_seeking = interaction.data["values"][0]
        self.language_seeking_display = _lookup_display(LANGUAGES, self.language_seeking)
        await interaction.response.defer()

    async def _seek_level_cb(self, interaction: Interaction):
        self.seeking_level = interaction.data["values"][0]
        self.seeking_level_display = _lookup_display(PROFICIENCY_LEVELS, self.seeking_level)
        await interaction.response.defer()

    @button(label="Next: Timezone & Details", style=ButtonStyle.primary, row=4)
    async def continue_button(self, interaction: Interaction, btn: Button):
        """Validate selections and move to step 3."""
        missing = []
        if not self.language_offering:
            missing.append("language you offer")
        if not self.offering_level:
            missing.append("your proficiency level")
        if not self.language_seeking:
            missing.append("language you're seeking")
        if not self.seeking_level:
            missing.append("partner's minimum level")

        if missing:
            await interaction.response.send_message(
                f"Please select: {', '.join(missing)}", ephemeral=True,
            )
            return

        step3_view = ExchangeStep3View(parent_view=self, introductions_channel_id=self.introductions_channel_id)
        embed = Embed(
            title="Introduction (Step 3/4)",
            description="Select your timezone and contact preference.",
            color=EXCHANGE_COLOR,
        )
        embed.add_field(
            name="Your Selection",
            value=(
                f"**Offering:** {self.language_offering_display} ({self.offering_level_display})\n"
                f"**Seeking:** {self.language_seeking_display} ({self.seeking_level_display})"
            ),
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=step3_view)

    async def on_timeout(self):
        logger.debug("ExchangeRequestView timed out")


class ExchangeStep3View(View):
    """Step 3/4: timezone, DM preference, country."""

    def __init__(self, parent_view: ExchangeRequestView, introductions_channel_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.parent_view = parent_view
        self.introductions_channel_id = introductions_channel_id

        self._build_selects()

    def _build_selects(self):
        """Build timezone, DM preference, and country selects."""
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
        self.parent_view.timezone = interaction.data["values"][0]
        await interaction.response.defer()

    async def _dm_cb(self, interaction: Interaction):
        self.parent_view.prefer_dm = interaction.data["values"][0] == "yes"
        await interaction.response.defer()

    async def _country_cb(self, interaction: Interaction):
        self.parent_view.country = interaction.data["values"][0]
        self.parent_view.country_display = _lookup_display(COUNTRIES, self.parent_view.country)
        await interaction.response.defer()

    @button(label="◀ Back", style=ButtonStyle.secondary, row=4)
    async def back_button(self, interaction: Interaction, btn: Button):
        """Go back to step 2."""
        embed = Embed(
            title="Introduction (Step 2/4)",
            description="Select the languages you offer and are looking for.",
            color=EXCHANGE_COLOR,
        )
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

    @button(label="Next: Add Details", style=ButtonStyle.primary, row=4)
    async def continue_button(self, interaction: Interaction, btn: Button):
        """Validate timezone and open the details modal."""
        if not self.parent_view.timezone:
            await interaction.response.send_message("Please select your timezone.", ephemeral=True)
            return

        modal = ExchangeDetailsModal(
            parent_view=self.parent_view,
            introductions_channel_id=self.introductions_channel_id,
        )
        await interaction.response.send_modal(modal)

    async def on_timeout(self):
        logger.debug("ExchangeStep3View timed out")
