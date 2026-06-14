"""Paginated fixtures view for $wcfixtures.

Builds 17 embed pages from the static fixtures data:
  - Pages  1–12: one per group (A–L), 6 matches each
  - Pages 13–14: Round of 32, split across two pages
  - Page  15:    Round of 16
  - Page  16:    Quarterfinals
  - Page  17:    Semifinals, Third Place Playoff, Final
"""

from datetime import UTC, datetime, timedelta, timezone

from discord import ButtonStyle, Color, Embed, Interaction
from discord.ui import Button, View

from .fixtures import FIXTURE_BY_ID, FIXTURES, GROUPS, Fixture

# Fixed Eastern Daylight Time offset for the tournament window (UTC-4),
# matching wcbet's kick-off handling.
_ET_OFFSET = timezone(timedelta(hours=-4))

# ── Flag emoji mapping ────────────────────────────────────────────────────────

TEAM_FLAGS: dict[str, str] = {
    "Mexico": "🇲🇽",
    "South Africa": "🇿🇦",
    "South Korea": "🇰🇷",
    "Czechia": "🇨🇿",
    "Canada": "🇨🇦",
    "Bosnia and Herzegovina": "🇧🇦",
    "Qatar": "🇶🇦",
    "Switzerland": "🇨🇭",
    "Brazil": "🇧🇷",
    "Morocco": "🇲🇦",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Haiti": "🇭🇹",
    "USA": "🇺🇸",
    "Paraguay": "🇵🇾",
    "Australia": "🇦🇺",
    "Türkiye": "🇹🇷",
    "Germany": "🇩🇪",
    "Curaçao": "🇨🇼",
    "Côte d'Ivoire": "🇨🇮",
    "Ecuador": "🇪🇨",
    "Netherlands": "🇳🇱",
    "Japan": "🇯🇵",
    "Sweden": "🇸🇪",
    "Tunisia": "🇹🇳",
    "Belgium": "🇧🇪",
    "Egypt": "🇪🇬",
    "Iran": "🇮🇷",
    "New Zealand": "🇳🇿",
    "Spain": "🇪🇸",
    "Cabo Verde": "🇨🇻",
    "Saudi Arabia": "🇸🇦",
    "Uruguay": "🇺🇾",
    "France": "🇫🇷",
    "Senegal": "🇸🇳",
    "Iraq": "🇮🇶",
    "Norway": "🇳🇴",
    "Argentina": "🇦🇷",
    "Algeria": "🇩🇿",
    "Austria": "🇦🇹",
    "Jordan": "🇯🇴",
    "Portugal": "🇵🇹",
    "DR Congo": "🇨🇩",
    "Uzbekistan": "🇺🇿",
    "Colombia": "🇨🇴",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Croatia": "🇭🇷",
    "Ghana": "🇬🇭",
    "Panama": "🇵🇦",
}

# ── Spanish / alternate name aliases ─────────────────────────────────────────
# Maps lower-cased Spanish (or common alternate) names to canonical English
# team names used in GROUPS/FIXTURES. Enables $wcf alemania, $wcf brasil, etc.

TEAM_ALIASES: dict[str, str] = {
    # Group A
    "méxico":                           "Mexico",
    "corea del sur":                    "South Korea",
    "corea":                            "South Korea",
    "república checa":                  "Czechia",
    "republica checa":                  "Czechia",
    "chequia":                          "Czechia",
    "sudáfrica":                        "South Africa",
    "sudafrica":                        "South Africa",
    "áfrica del sur":                   "South Africa",
    "africa del sur":                   "South Africa",
    # Group B
    "canadá":                           "Canada",
    "bosnia y herzegovina":             "Bosnia and Herzegovina",
    "bosnia y hercegovina":             "Bosnia and Herzegovina",
    "catar":                            "Qatar",
    "suiza":                            "Switzerland",
    # Group C
    "brasil":                           "Brazil",
    "marruecos":                        "Morocco",
    "escocia":                          "Scotland",
    "haití":                            "Haiti",
    "haiti":                            "Haiti",
    # Group D
    "estados unidos":                   "USA",
    "eeuu":                             "USA",
    "ee.uu.":                           "USA",
    "turquía":                          "Türkiye",
    "turquia":                          "Türkiye",
    "turkey":                           "Türkiye",
    # Group E
    "alemania":                         "Germany",
    "curazao":                          "Curaçao",
    "costa de marfil":                  "Côte d'Ivoire",
    "marfil":                           "Côte d'Ivoire",
    # Group F
    "países bajos":                     "Netherlands",
    "paises bajos":                     "Netherlands",
    "holanda":                          "Netherlands",
    "suecia":                           "Sweden",
    "túnez":                            "Tunisia",
    "tunez":                            "Tunisia",
    # Group G
    "bélgica":                          "Belgium",
    "belgica":                          "Belgium",
    "egipto":                           "Egypt",
    "nueva zelanda":                    "New Zealand",
    "nueva zelandia":                   "New Zealand",
    # Group H
    "españa":                           "Spain",
    "espana":                           "Spain",
    "arabia saudita":                   "Saudi Arabia",
    "arabia saudí":                     "Saudi Arabia",
    "arabia saudi":                     "Saudi Arabia",
    # Group I
    "francia":                          "France",
    "irak":                             "Iraq",
    "noruega":                          "Norway",
    # Group J
    "argelia":                          "Algeria",
    "jordania":                         "Jordan",
    # Group K
    "república democrática del congo":  "DR Congo",
    "republica democratica del congo":  "DR Congo",
    "congo rd":                         "DR Congo",
    "uzbekistán":                       "Uzbekistan",
    # Group L
    "inglaterra":                       "England",
    "croacia":                          "Croatia",
    "panamá":                           "Panama",
}

# ── Page definitions ──────────────────────────────────────────────────────────

# Each entry is (title, color, list_of_match_ids)
_GROUP_STAGE_COLOR = Color.blue()
_R32_COLOR = Color.orange()
_LATE_KO_COLOR = Color.gold()

_PAGES: list[tuple[str, Color, list[int]]] = []

# Pages 1-12: one per group
for _grp in "ABCDEFGHIJKL":
    _ids = [f["match_id"] for f in FIXTURES if f["group"] == _grp]
    _PAGES.append((f"⚽  Group {_grp}", _GROUP_STAGE_COLOR, _ids))

# Pages 13-14: Round of 32 split in half
_r32_ids = [f["match_id"] for f in FIXTURES if f["stage"] == "Round of 32"]
_PAGES.append(("🏆  Round of 32 — Part 1", _R32_COLOR, _r32_ids[:8]))
_PAGES.append(("🏆  Round of 32 — Part 2", _R32_COLOR, _r32_ids[8:]))

# Page 15: Round of 16
_r16_ids = [f["match_id"] for f in FIXTURES if f["stage"] == "Round of 16"]
_PAGES.append(("🏆  Round of 16", _R32_COLOR, _r16_ids))

# Page 16: Quarterfinals
_qf_ids = [f["match_id"] for f in FIXTURES if f["stage"] == "Quarterfinal"]
_PAGES.append(("🏆  Quarterfinals", _LATE_KO_COLOR, _qf_ids))

# Page 17: Semis + 3rd + Final
_late_ids = [
    f["match_id"]
    for f in FIXTURES
    if f["stage"] in {"Semifinal", "Third Place Playoff", "Final"}
]
_PAGES.append(("🏆  Semifinals · 3rd Place · Final", _LATE_KO_COLOR, _late_ids))

TOTAL_PAGES = len(_PAGES)  # 17


# ── Jump-target resolution ────────────────────────────────────────────────────

def resolve_page(query: str) -> int:
    """Return a 0-based page index for a user query, or 0 if unrecognised.

    Accepts:
    - A single group letter: "A"–"L"
    - A team name (case-insensitive, partial OK): "brazil", "south korea"
    - Stage keywords: "r32", "r16", "quarter", "semi", "final", "3rd"
    """
    q = query.strip().lower()

    # Group letter
    if len(q) == 1 and q.upper() in "ABCDEFGHIJKL":
        return "ABCDEFGHIJKL".index(q.upper())

    # Stage keywords
    keyword_map: dict[str, int] = {
        "r32": 12, "round of 32": 12,
        "r16": 14, "round of 16": 14,
        "quarter": 15, "qf": 15,
        "semi": 16, "sf": 16,
        "3rd": 16, "third": 16,
        "final": 16,
    }
    for kw, page in keyword_map.items():
        if kw in q:
            return page

    # Team name — English (substring match)
    for team in TEAM_FLAGS:
        if q in team.lower():
            for grp, teams in GROUPS.items():
                if team in teams:
                    return "ABCDEFGHIJKL".index(grp)

    # Team name — Spanish / alternate aliases (substring match both ways)
    for alias, canonical in TEAM_ALIASES.items():
        if q in alias or alias in q:
            for grp, teams in GROUPS.items():
                if canonical in teams:
                    return "ABCDEFGHIJKL".index(grp)

    return 0


# ── Embed builder ─────────────────────────────────────────────────────────────

def _team_label(name: str) -> str:
    """Return 'FLAG Name' for known teams, or just 'Name' for placeholders."""
    flag = TEAM_FLAGS.get(name, "")
    return f"{flag} {name}".strip()


def _fmt_date(date_str: str) -> str:
    """'2026-06-11' → 'Jun 11'"""
    months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    _, m, d = date_str.split("-")
    return f"{months[int(m) - 1]} {int(d):02d}"


def _kickoff_ts(fixture: Fixture) -> int | None:
    """Unix timestamp for the fixture kick-off, or None if the time is TBD.

    The kick-off is stored as an Eastern date + time; the tournament runs
    during EDT (UTC-4). Returns an epoch suitable for a Discord ``<t:>``
    timestamp, which renders in each viewer's own timezone.
    """
    if fixture["time_et"] == "TBD":
        return None
    local = datetime.strptime(f"{fixture['date']} {fixture['time_et']}", "%Y-%m-%d %H:%M")
    return int(local.replace(tzinfo=_ET_OFFSET).astimezone(UTC).timestamp())


def _match_line(fixture: Fixture) -> str:
    """Single formatted line for one match."""
    home = _team_label(fixture["home"])
    away = _team_label(fixture["away"])
    venue = fixture["venue"]
    city = fixture["city"]
    ts = _kickoff_ts(fixture)
    when = f"<t:{ts}:f>" if ts is not None else f"`{_fmt_date(fixture['date'])} · TBD`"
    return f"{when}\n{home} **vs** {away}\n-# {venue} · {city}"


def build_embed(page: int) -> Embed:
    """Build the embed for the given 0-based page index."""
    title, color, match_ids = _PAGES[page]

    lines: list[str] = []

    # Group header: show participating teams
    grp_letter = title[-1] if title.startswith("⚽") else None
    if grp_letter and grp_letter in GROUPS:
        teams_line = "  ·  ".join(_team_label(t) for t in GROUPS[grp_letter])
        lines.append(teams_line)
        lines.append("")  # blank line before matches

    for mid in match_ids:
        fixture = FIXTURE_BY_ID[mid]
        lines.append(_match_line(fixture))
        lines.append("")  # spacing between matches

    description = "\n".join(lines).rstrip()

    embed = Embed(title=title, description=description, color=color)
    embed.set_footer(
        text=(
            f"Page {page + 1}/{TOTAL_PAGES}  ·  "
            "Use ◀ ▶ to navigate  ·  "
            "$wcf [group/team/stage] to jump"
        )
    )
    return embed


# ── View ──────────────────────────────────────────────────────────────────────

class FixturesView(View):
    """Paginated ◀/▶ navigator for World Cup fixtures.

    Restricts button interactions to the user who invoked the command.
    On timeout the buttons are disabled so the embed stays readable.
    """

    def __init__(self, invoker_id: int, page: int = 0, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.invoker_id = invoker_id
        self.page = page
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()

        prev_btn = Button(
            label="◀",
            style=ButtonStyle.secondary,
            disabled=self.page <= 0,
            row=0,
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        next_btn = Button(
            label="▶",
            style=ButtonStyle.secondary,
            disabled=self.page >= TOTAL_PAGES - 1,
            row=0,
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Only the person who ran this command can flip pages.",
                ephemeral=True,
            )
            return False
        return True

    async def _prev(self, interaction: Interaction) -> None:
        self.page = max(0, self.page - 1)
        self._rebuild()
        await interaction.response.edit_message(embed=build_embed(self.page), view=self)

    async def _next(self, interaction: Interaction) -> None:
        self.page = min(TOTAL_PAGES - 1, self.page + 1)
        self._rebuild()
        await interaction.response.edit_message(embed=build_embed(self.page), view=self)

    async def on_timeout(self) -> None:
        """Disable buttons when the view expires."""
        for item in self.children:
            if isinstance(item, Button):
                item.disabled = True
