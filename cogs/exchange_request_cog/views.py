import discord
from discord.ui import View, Select, Button, select, button
from discord import SelectOption, Interaction, ButtonStyle, Embed

from .config import LANGUAGES, PROFICIENCY_LEVELS, TIMEZONES
from .modals import ExchangeDetailsModal


class ExchangeRequestView(View):
    """Multi-step view for collecting exchange partner request data."""

    def __init__(self, results_channel_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.results_channel_id = results_channel_id

        # Store user selections
        self.language_offering: str | None = None
        self.offering_level: str | None = None
        self.language_seeking: str | None = None
        self.seeking_level: str | None = None
        self.timezone: str | None = None
        self.prefer_dm: bool = False

        # Display values for the final embed
        self.language_offering_display: str | None = None
        self.offering_level_display: str | None = None
        self.language_seeking_display: str | None = None
        self.seeking_level_display: str | None = None
        self.timezone_display: str | None = None

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
        """Move to second step with timezone and DM preference."""
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

        # Show second step view
        step2_view = ExchangeRequestStep2View(
            parent_view=self,
            results_channel_id=self.results_channel_id
        )
        embed = self._create_step2_embed()
        await interaction.response.edit_message(embed=embed, view=step2_view)

    def _create_step2_embed(self) -> Embed:
        """Create embed for step 2."""
        embed = Embed(
            title="Exchange Partner Request (Step 2/3)",
            description="Select your timezone and contact preference.",
            color=discord.Color.blue()
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


class ExchangeRequestStep2View(View):
    """Second step: timezone and DM preference."""

    def __init__(self, parent_view: ExchangeRequestView, results_channel_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.parent_view = parent_view
        self.results_channel_id = results_channel_id
        self.prefer_dm = False

        self._build_selects()

    def _build_selects(self):
        """Build timezone select."""
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

    async def tz_callback(self, interaction: Interaction):
        self.parent_view.timezone = interaction.data["values"][0]
        self.parent_view.timezone_display = next(
            (label for label, value in TIMEZONES if value == self.parent_view.timezone),
            self.parent_view.timezone
        )
        await interaction.response.defer()

    @button(label="Prefer DM Contact", style=ButtonStyle.secondary, emoji="📩", row=1)
    async def dm_toggle_button(self, interaction: Interaction, btn: Button):
        """Toggle DM preference."""
        self.prefer_dm = not self.prefer_dm
        self.parent_view.prefer_dm = self.prefer_dm

        if self.prefer_dm:
            btn.style = ButtonStyle.success
            btn.label = "Prefer DM Contact ✓"
        else:
            btn.style = ButtonStyle.secondary
            btn.label = "Prefer DM Contact"

        await interaction.response.edit_message(view=self)

    @button(label="◀ Back", style=ButtonStyle.secondary, row=2)
    async def back_button(self, interaction: Interaction, btn: Button):
        """Go back to step 1."""
        embed = Embed(
            title="Exchange Partner Request (Step 1/3)",
            description="Select the languages you offer and are looking for.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

    @button(label="Next: Add Details", style=ButtonStyle.primary, row=2)
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
            results_channel_id=self.results_channel_id
        )
        await interaction.response.send_modal(modal)
