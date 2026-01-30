import discord
from discord.ui import View, Select, Button, select, button
from discord import SelectOption, Interaction, ButtonStyle, Embed

from .config import LANGUAGES, PROFICIENCY_LEVELS, TIMEZONES, COUNTRIES, INTRO_COLOR, EXCHANGE_COLOR
from .modals import ExchangeDetailsModal, IntroOnlyModal


class IntroStartView(View):
    """Initial view asking if user wants to find an exchange partner."""

    def __init__(self, introductions_channel_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.introductions_channel_id = introductions_channel_id
        self.seeking_exchange: bool | None = None

        self._build_select()

    def _build_select(self):
        """Build the yes/no select menu."""
        options = [
            SelectOption(
                label="Yes",
                value="yes",
                description="I want to find a language exchange partner"
            ),
            SelectOption(
                label="No",
                value="no",
                description="I just want to introduce myself"
            ),
        ]
        self.exchange_select = Select(
            placeholder="Looking for an exchange partner?",
            options=options,
            custom_id="seeking_exchange",
            row=0
        )
        self.exchange_select.callback = self.exchange_select_callback
        self.add_item(self.exchange_select)

    async def exchange_select_callback(self, interaction: Interaction):
        self.seeking_exchange = interaction.data["values"][0] == "yes"
        await interaction.response.defer()

    @button(label="Continue →", style=ButtonStyle.primary, row=1)
    async def continue_button(self, interaction: Interaction, btn: Button):
        """Branch to appropriate flow based on selection."""
        if self.seeking_exchange is None:
            await interaction.response.send_message(
                "Please select whether you're looking for an exchange partner.",
                ephemeral=True
            )
            return

        if self.seeking_exchange:
            # Show language selection view (Step 2/4)
            view = ExchangeRequestView(introductions_channel_id=self.introductions_channel_id)
            embed = Embed(
                title="Introduction (Step 2/4)",
                description=(
                    "Great! Let's find you a language exchange partner.\n\n"
                    "**Step 2:** Select the languages you offer and are looking for."
                ),
                color=EXCHANGE_COLOR
            )
            embed.set_footer(text="This form will expire in 5 minutes")
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            # Show simple intro modal
            modal = IntroOnlyModal(introductions_channel_id=self.introductions_channel_id)
            await interaction.response.send_modal(modal)


class ExchangeRequestView(View):
    """Multi-step view for collecting exchange partner request data (Step 2/4)."""

    def __init__(self, introductions_channel_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.introductions_channel_id = introductions_channel_id

        # Store user selections
        self.language_offering: str | None = None
        self.offering_level: str | None = None
        self.language_seeking: str | None = None
        self.seeking_level: str | None = None
        self.timezone: str | None = None
        self.prefer_dm: bool = False
        self.country: str | None = None

        # Display values for the final embed
        self.language_offering_display: str | None = None
        self.offering_level_display: str | None = None
        self.language_seeking_display: str | None = None
        self.seeking_level_display: str | None = None
        self.timezone_display: str | None = None
        self.country_display: str | None = None

        self._build_selects()

    def _build_selects(self):
        """Build all select menus."""
        # Language offering select
        lang_offer_options = [
            SelectOption(label=label, value=value)
            for label, value in LANGUAGES
        ]
        self.lang_offer_select = Select(
            placeholder="Language you offer...",
            options=lang_offer_options,
            custom_id="lang_offer",
            row=0
        )
        self.lang_offer_select.callback = self.lang_offer_callback
        self.add_item(self.lang_offer_select)

        # Offering proficiency level select
        offer_level_options = [
            SelectOption(label=label, value=value)
            for label, value in PROFICIENCY_LEVELS
        ]
        self.offer_level_select = Select(
            placeholder="Your level in that language...",
            options=offer_level_options,
            custom_id="offer_level",
            row=1
        )
        self.offer_level_select.callback = self.offer_level_callback
        self.add_item(self.offer_level_select)

        # Language seeking select
        lang_seek_options = [
            SelectOption(label=label, value=value)
            for label, value in LANGUAGES
        ]
        self.lang_seek_select = Select(
            placeholder="Language you're looking for...",
            options=lang_seek_options,
            custom_id="lang_seek",
            row=2
        )
        self.lang_seek_select.callback = self.lang_seek_callback
        self.add_item(self.lang_seek_select)

        # Seeking proficiency level select
        seek_level_options = [
            SelectOption(label=label, value=value)
            for label, value in PROFICIENCY_LEVELS
        ]
        self.seek_level_select = Select(
            placeholder="Partner's minimum level...",
            options=seek_level_options,
            custom_id="seek_level",
            row=3
        )
        self.seek_level_select.callback = self.seek_level_callback
        self.add_item(self.seek_level_select)

    async def lang_offer_callback(self, interaction: Interaction):
        self.language_offering = interaction.data["values"][0]
        self.language_offering_display = next(
            (label for label, value in LANGUAGES if value == self.language_offering),
            self.language_offering
        )
        await interaction.response.defer()

    async def offer_level_callback(self, interaction: Interaction):
        self.offering_level = interaction.data["values"][0]
        self.offering_level_display = next(
            (label for label, value in PROFICIENCY_LEVELS if value == self.offering_level),
            self.offering_level
        )
        await interaction.response.defer()

    async def lang_seek_callback(self, interaction: Interaction):
        self.language_seeking = interaction.data["values"][0]
        self.language_seeking_display = next(
            (label for label, value in LANGUAGES if value == self.language_seeking),
            self.language_seeking
        )
        await interaction.response.defer()

    async def seek_level_callback(self, interaction: Interaction):
        self.seeking_level = interaction.data["values"][0]
        self.seeking_level_display = next(
            (label for label, value in PROFICIENCY_LEVELS if value == self.seeking_level),
            self.seeking_level
        )
        await interaction.response.defer()

    @button(label="Next: Timezone & Details", style=ButtonStyle.primary, row=4)
    async def continue_button(self, interaction: Interaction, btn: Button):
        """Move to third step with timezone and DM preference."""
        # Validate required fields
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
                f"Please select: {', '.join(missing)}",
                ephemeral=True
            )
            return

        # Show third step view
        step3_view = ExchangeRequestStep3View(
            parent_view=self,
            introductions_channel_id=self.introductions_channel_id
        )
        embed = self._create_step3_embed()
        await interaction.response.edit_message(embed=embed, view=step3_view)

    def _create_step3_embed(self) -> Embed:
        """Create embed for step 3."""
        embed = Embed(
            title="Introduction (Step 3/4)",
            description="Select your timezone and contact preference.",
            color=EXCHANGE_COLOR
        )
        embed.add_field(
            name="Your Selection",
            value=(
                f"**Offering:** {self.language_offering_display} ({self.offering_level_display})\n"
                f"**Seeking:** {self.language_seeking_display} ({self.seeking_level_display})"
            ),
            inline=False
        )
        return embed


class ExchangeRequestStep3View(View):
    """Third step: timezone and DM preference (Step 3/4)."""

    def __init__(self, parent_view: ExchangeRequestView, introductions_channel_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.parent_view = parent_view
        self.introductions_channel_id = introductions_channel_id
        self.prefer_dm = False

        self._build_selects()

    def _build_selects(self):
        """Build timezone and DM preference selects."""
        # Timezone select
        tz_options = [
            SelectOption(label=label, value=value)
            for label, value in TIMEZONES
        ]
        self.tz_select = Select(
            placeholder="Select your timezone...",
            options=tz_options,
            custom_id="timezone",
            row=0
        )
        self.tz_select.callback = self.tz_callback
        self.add_item(self.tz_select)

        # DM preference select
        dm_options = [
            SelectOption(label="Yes", value="yes", description="Others should contact you via DM"),
            SelectOption(label="No", value="no", description="Others can mention you in the channel"),
        ]
        self.dm_select = Select(
            placeholder="Prefer DM contact?",
            options=dm_options,
            custom_id="prefer_dm",
            row=1
        )
        self.dm_select.callback = self.dm_callback
        self.add_item(self.dm_select)

        # Country preference select
        country_options = [
            SelectOption(label=label, value=value)
            for label, value in COUNTRIES
        ]
        self.country_select = Select(
            placeholder="Partner's country preference...",
            options=country_options,
            custom_id="country",
            row=2
        )
        self.country_select.callback = self.country_callback
        self.add_item(self.country_select)

    async def tz_callback(self, interaction: Interaction):
        self.parent_view.timezone = interaction.data["values"][0]
        self.parent_view.timezone_display = next(
            (label for label, value in TIMEZONES if value == self.parent_view.timezone),
            self.parent_view.timezone
        )
        await interaction.response.defer()

    async def dm_callback(self, interaction: Interaction):
        self.parent_view.prefer_dm = interaction.data["values"][0] == "yes"
        await interaction.response.defer()

    async def country_callback(self, interaction: Interaction):
        self.parent_view.country = interaction.data["values"][0]
        self.parent_view.country_display = next(
            (label for label, value in COUNTRIES if value == self.parent_view.country),
            self.parent_view.country
        )
        await interaction.response.defer()

    @button(label="◀ Back", style=ButtonStyle.secondary, row=4)
    async def back_button(self, interaction: Interaction, btn: Button):
        """Go back to step 2."""
        embed = Embed(
            title="Introduction (Step 2/4)",
            description="Select the languages you offer and are looking for.",
            color=EXCHANGE_COLOR
        )
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

    @button(label="Next: Add Details", style=ButtonStyle.primary, row=4)
    async def continue_button(self, interaction: Interaction, btn: Button):
        """Open modal for free-text details."""
        if not self.parent_view.timezone:
            await interaction.response.send_message(
                "Please select your timezone.",
                ephemeral=True
            )
            return

        modal = ExchangeDetailsModal(
            parent_view=self.parent_view,
            introductions_channel_id=self.introductions_channel_id
        )
        await interaction.response.send_modal(modal)
