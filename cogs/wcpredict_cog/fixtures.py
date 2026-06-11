"""2026 FIFA World Cup fixtures — all 104 matches.

Source: FIFA / Sports Illustrated (verified May 2026).

All kick-off times are Eastern Time (ET / UTC−4, June–July 2026).
Times marked ``"TBD"`` are not yet confirmed by FIFA.

Team names in group-stage fixtures are the actual competing sides.
Knockout-stage ``home`` / ``away`` use bracket placeholders:
  - ``"Winner Group X"`` / ``"Runner-up Group X"``  — Round of 32
  - ``"Best 3rd (X/Y/…)"``                          — best third-place slot
  - ``"Winner Match <id>"`` / ``"Loser Match <id>"`` — later rounds
"""

from typing import TypedDict


class Fixture(TypedDict):
    match_id: int      # 1-104, sequential by stage then schedule order
    stage: str         # "Group Stage" | "Round of 32" | "Round of 16" |
                       # "Quarterfinal" | "Semifinal" | "Third Place Playoff" | "Final"
    group: str | None  # "A"-"L" for group stage; None for knockouts
    date: str          # ISO 8601: YYYY-MM-DD (Eastern date)
    time_et: str       # HH:MM 24-hour ET, or "TBD" for unconfirmed knockout times
    home: str          # team name or bracket placeholder
    away: str          # team name or bracket placeholder
    venue: str
    city: str


# ── Team rosters by group ────────────────────────────────────────────────────

GROUPS: dict[str, list[str]] = {
    "A": ["Mexico", "South Africa", "South Korea", "Czechia"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Scotland", "Haiti"],
    "D": ["USA", "Paraguay", "Australia", "Türkiye"],
    "E": ["Germany", "Curaçao", "Côte d'Ivoire", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cabo Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

ALL_TEAMS: list[str] = [team for teams in GROUPS.values() for team in teams]

# ── All 104 fixtures ─────────────────────────────────────────────────────────

FIXTURES: list[Fixture] = [
    # ── GROUP A ──────────────────────────────────────────────────────────────
    {
        "match_id": 1, "stage": "Group Stage", "group": "A",
        "date": "2026-06-11", "time_et": "15:00",
        "home": "Mexico", "away": "South Africa",
        "venue": "Estadio Azteca", "city": "Mexico City",
    },
    {
        "match_id": 2, "stage": "Group Stage", "group": "A",
        "date": "2026-06-11", "time_et": "22:00",
        "home": "South Korea", "away": "Czechia",
        "venue": "Estadio Akron", "city": "Zapopan",
    },
    {
        "match_id": 3, "stage": "Group Stage", "group": "A",
        "date": "2026-06-18", "time_et": "12:00",
        "home": "Czechia", "away": "South Africa",
        "venue": "Mercedes-Benz Stadium", "city": "Atlanta",
    },
    {
        "match_id": 4, "stage": "Group Stage", "group": "A",
        "date": "2026-06-18", "time_et": "21:00",
        "home": "Mexico", "away": "South Korea",
        "venue": "Estadio Akron", "city": "Zapopan",
    },
    {
        "match_id": 5, "stage": "Group Stage", "group": "A",
        "date": "2026-06-24", "time_et": "21:00",
        "home": "Czechia", "away": "Mexico",
        "venue": "Estadio Azteca", "city": "Mexico City",
    },
    {
        "match_id": 6, "stage": "Group Stage", "group": "A",
        "date": "2026-06-24", "time_et": "21:00",
        "home": "South Africa", "away": "South Korea",
        "venue": "Estadio BBVA", "city": "Guadalupe",
    },

    # ── GROUP B ──────────────────────────────────────────────────────────────
    {
        "match_id": 7, "stage": "Group Stage", "group": "B",
        "date": "2026-06-12", "time_et": "15:00",
        "home": "Canada", "away": "Bosnia and Herzegovina",
        "venue": "BMO Field", "city": "Toronto",
    },
    {
        "match_id": 8, "stage": "Group Stage", "group": "B",
        "date": "2026-06-13", "time_et": "15:00",
        "home": "Qatar", "away": "Switzerland",
        "venue": "Levi's Stadium", "city": "Santa Clara",
    },
    {
        "match_id": 9, "stage": "Group Stage", "group": "B",
        "date": "2026-06-18", "time_et": "15:00",
        "home": "Switzerland", "away": "Bosnia and Herzegovina",
        "venue": "SoFi Stadium", "city": "Inglewood",
    },
    {
        "match_id": 10, "stage": "Group Stage", "group": "B",
        "date": "2026-06-18", "time_et": "18:00",
        "home": "Canada", "away": "Qatar",
        "venue": "BC Place", "city": "Vancouver",
    },
    {
        "match_id": 11, "stage": "Group Stage", "group": "B",
        "date": "2026-06-24", "time_et": "15:00",
        "home": "Switzerland", "away": "Canada",
        "venue": "BC Place", "city": "Vancouver",
    },
    {
        "match_id": 12, "stage": "Group Stage", "group": "B",
        "date": "2026-06-24", "time_et": "15:00",
        "home": "Bosnia and Herzegovina", "away": "Qatar",
        "venue": "Lumen Field", "city": "Seattle",
    },

    # ── GROUP C ──────────────────────────────────────────────────────────────
    {
        "match_id": 13, "stage": "Group Stage", "group": "C",
        "date": "2026-06-13", "time_et": "18:00",
        "home": "Brazil", "away": "Morocco",
        "venue": "MetLife Stadium", "city": "East Rutherford",
    },
    {
        "match_id": 14, "stage": "Group Stage", "group": "C",
        "date": "2026-06-13", "time_et": "21:00",
        "home": "Haiti", "away": "Scotland",
        "venue": "Gillette Stadium", "city": "Foxborough",
    },
    {
        "match_id": 15, "stage": "Group Stage", "group": "C",
        "date": "2026-06-19", "time_et": "18:00",
        "home": "Scotland", "away": "Morocco",
        "venue": "Gillette Stadium", "city": "Foxborough",
    },
    {
        "match_id": 16, "stage": "Group Stage", "group": "C",
        "date": "2026-06-19", "time_et": "20:30",
        "home": "Brazil", "away": "Haiti",
        "venue": "Lincoln Financial Field", "city": "Philadelphia",
    },
    {
        "match_id": 17, "stage": "Group Stage", "group": "C",
        "date": "2026-06-24", "time_et": "18:00",
        "home": "Scotland", "away": "Brazil",
        "venue": "Hard Rock Stadium", "city": "Miami Gardens",
    },
    {
        "match_id": 18, "stage": "Group Stage", "group": "C",
        "date": "2026-06-24", "time_et": "18:00",
        "home": "Morocco", "away": "Haiti",
        "venue": "Mercedes-Benz Stadium", "city": "Atlanta",
    },

    # ── GROUP D ──────────────────────────────────────────────────────────────
    {
        "match_id": 19, "stage": "Group Stage", "group": "D",
        "date": "2026-06-12", "time_et": "21:00",
        "home": "USA", "away": "Paraguay",
        "venue": "SoFi Stadium", "city": "Inglewood",
    },
    {
        # 00:00 ET Jun 14 = 9 pm PT Jun 13 — evening kickoff at a Vancouver venue
        "match_id": 20, "stage": "Group Stage", "group": "D",
        "date": "2026-06-14", "time_et": "00:00",
        "home": "Australia", "away": "Türkiye",
        "venue": "BC Place", "city": "Vancouver",
    },
    {
        "match_id": 21, "stage": "Group Stage", "group": "D",
        "date": "2026-06-19", "time_et": "23:00",
        "home": "Türkiye", "away": "Paraguay",
        "venue": "Levi's Stadium", "city": "Santa Clara",
    },
    {
        "match_id": 22, "stage": "Group Stage", "group": "D",
        "date": "2026-06-19", "time_et": "15:00",
        "home": "USA", "away": "Australia",
        "venue": "Lumen Field", "city": "Seattle",
    },
    {
        "match_id": 23, "stage": "Group Stage", "group": "D",
        "date": "2026-06-25", "time_et": "22:00",
        "home": "Türkiye", "away": "USA",
        "venue": "SoFi Stadium", "city": "Inglewood",
    },
    {
        "match_id": 24, "stage": "Group Stage", "group": "D",
        "date": "2026-06-25", "time_et": "22:00",
        "home": "Paraguay", "away": "Australia",
        "venue": "Levi's Stadium", "city": "Santa Clara",
    },

    # ── GROUP E ──────────────────────────────────────────────────────────────
    {
        "match_id": 25, "stage": "Group Stage", "group": "E",
        "date": "2026-06-14", "time_et": "13:00",
        "home": "Germany", "away": "Curaçao",
        "venue": "NRG Stadium", "city": "Houston",
    },
    {
        "match_id": 26, "stage": "Group Stage", "group": "E",
        "date": "2026-06-14", "time_et": "19:00",
        "home": "Côte d'Ivoire", "away": "Ecuador",
        "venue": "Lincoln Financial Field", "city": "Philadelphia",
    },
    {
        "match_id": 27, "stage": "Group Stage", "group": "E",
        "date": "2026-06-20", "time_et": "16:00",
        "home": "Germany", "away": "Côte d'Ivoire",
        "venue": "BMO Field", "city": "Toronto",
    },
    {
        "match_id": 28, "stage": "Group Stage", "group": "E",
        "date": "2026-06-20", "time_et": "20:00",
        "home": "Ecuador", "away": "Curaçao",
        "venue": "Arrowhead Stadium", "city": "Kansas City",
    },
    {
        "match_id": 29, "stage": "Group Stage", "group": "E",
        "date": "2026-06-25", "time_et": "16:00",
        "home": "Ecuador", "away": "Germany",
        "venue": "MetLife Stadium", "city": "East Rutherford",
    },
    {
        "match_id": 30, "stage": "Group Stage", "group": "E",
        "date": "2026-06-25", "time_et": "16:00",
        "home": "Curaçao", "away": "Côte d'Ivoire",
        "venue": "Lincoln Financial Field", "city": "Philadelphia",
    },

    # ── GROUP F ──────────────────────────────────────────────────────────────
    {
        "match_id": 31, "stage": "Group Stage", "group": "F",
        "date": "2026-06-14", "time_et": "16:00",
        "home": "Netherlands", "away": "Japan",
        "venue": "AT&T Stadium", "city": "Arlington",
    },
    {
        "match_id": 32, "stage": "Group Stage", "group": "F",
        "date": "2026-06-14", "time_et": "22:00",
        "home": "Sweden", "away": "Tunisia",
        "venue": "Estadio BBVA", "city": "Guadalupe",
    },
    {
        "match_id": 33, "stage": "Group Stage", "group": "F",
        "date": "2026-06-20", "time_et": "13:00",
        "home": "Netherlands", "away": "Sweden",
        "venue": "NRG Stadium", "city": "Houston",
    },
    {
        # 00:00 ET Jun 21 = 11 pm CDT Jun 20 at a Mexican venue
        "match_id": 34, "stage": "Group Stage", "group": "F",
        "date": "2026-06-21", "time_et": "00:00",
        "home": "Tunisia", "away": "Japan",
        "venue": "Estadio BBVA", "city": "Guadalupe",
    },
    {
        "match_id": 35, "stage": "Group Stage", "group": "F",
        "date": "2026-06-25", "time_et": "19:00",
        "home": "Tunisia", "away": "Netherlands",
        "venue": "AT&T Stadium", "city": "Arlington",
    },
    {
        "match_id": 36, "stage": "Group Stage", "group": "F",
        "date": "2026-06-25", "time_et": "19:00",
        "home": "Japan", "away": "Sweden",
        "venue": "Arrowhead Stadium", "city": "Kansas City",
    },

    # ── GROUP G ──────────────────────────────────────────────────────────────
    {
        "match_id": 37, "stage": "Group Stage", "group": "G",
        "date": "2026-06-15", "time_et": "15:00",
        "home": "Belgium", "away": "Egypt",
        "venue": "Lumen Field", "city": "Seattle",
    },
    {
        "match_id": 38, "stage": "Group Stage", "group": "G",
        "date": "2026-06-15", "time_et": "21:00",
        "home": "Iran", "away": "New Zealand",
        "venue": "SoFi Stadium", "city": "Inglewood",
    },
    {
        "match_id": 39, "stage": "Group Stage", "group": "G",
        "date": "2026-06-21", "time_et": "15:00",
        "home": "Belgium", "away": "Iran",
        "venue": "SoFi Stadium", "city": "Inglewood",
    },
    {
        "match_id": 40, "stage": "Group Stage", "group": "G",
        "date": "2026-06-21", "time_et": "21:00",
        "home": "New Zealand", "away": "Egypt",
        "venue": "BC Place", "city": "Vancouver",
    },
    {
        "match_id": 41, "stage": "Group Stage", "group": "G",
        "date": "2026-06-26", "time_et": "23:00",
        "home": "New Zealand", "away": "Belgium",
        "venue": "BC Place", "city": "Vancouver",
    },
    {
        "match_id": 42, "stage": "Group Stage", "group": "G",
        "date": "2026-06-26", "time_et": "23:00",
        "home": "Egypt", "away": "Iran",
        "venue": "Lumen Field", "city": "Seattle",
    },

    # ── GROUP H ──────────────────────────────────────────────────────────────
    {
        "match_id": 43, "stage": "Group Stage", "group": "H",
        "date": "2026-06-15", "time_et": "12:00",
        "home": "Spain", "away": "Cabo Verde",
        "venue": "Mercedes-Benz Stadium", "city": "Atlanta",
    },
    {
        "match_id": 44, "stage": "Group Stage", "group": "H",
        "date": "2026-06-15", "time_et": "18:00",
        "home": "Saudi Arabia", "away": "Uruguay",
        "venue": "Hard Rock Stadium", "city": "Miami Gardens",
    },
    {
        "match_id": 45, "stage": "Group Stage", "group": "H",
        "date": "2026-06-21", "time_et": "12:00",
        "home": "Spain", "away": "Saudi Arabia",
        "venue": "Mercedes-Benz Stadium", "city": "Atlanta",
    },
    {
        "match_id": 46, "stage": "Group Stage", "group": "H",
        "date": "2026-06-21", "time_et": "18:00",
        "home": "Uruguay", "away": "Cabo Verde",
        "venue": "Hard Rock Stadium", "city": "Miami Gardens",
    },
    {
        "match_id": 47, "stage": "Group Stage", "group": "H",
        "date": "2026-06-26", "time_et": "20:00",
        "home": "Uruguay", "away": "Spain",
        "venue": "NRG Stadium", "city": "Houston",
    },
    {
        "match_id": 48, "stage": "Group Stage", "group": "H",
        "date": "2026-06-26", "time_et": "20:00",
        "home": "Cabo Verde", "away": "Saudi Arabia",
        "venue": "Estadio Akron", "city": "Zapopan",
    },

    # ── GROUP I ──────────────────────────────────────────────────────────────
    {
        "match_id": 49, "stage": "Group Stage", "group": "I",
        "date": "2026-06-16", "time_et": "15:00",
        "home": "France", "away": "Senegal",
        "venue": "MetLife Stadium", "city": "East Rutherford",
    },
    {
        "match_id": 50, "stage": "Group Stage", "group": "I",
        "date": "2026-06-16", "time_et": "18:00",
        "home": "Iraq", "away": "Norway",
        "venue": "Gillette Stadium", "city": "Foxborough",
    },
    {
        "match_id": 51, "stage": "Group Stage", "group": "I",
        "date": "2026-06-22", "time_et": "17:00",
        "home": "France", "away": "Iraq",
        "venue": "Lincoln Financial Field", "city": "Philadelphia",
    },
    {
        "match_id": 52, "stage": "Group Stage", "group": "I",
        "date": "2026-06-22", "time_et": "20:00",
        "home": "Norway", "away": "Senegal",
        "venue": "MetLife Stadium", "city": "East Rutherford",
    },
    {
        "match_id": 53, "stage": "Group Stage", "group": "I",
        "date": "2026-06-26", "time_et": "15:00",
        "home": "Norway", "away": "France",
        "venue": "Gillette Stadium", "city": "Foxborough",
    },
    {
        "match_id": 54, "stage": "Group Stage", "group": "I",
        "date": "2026-06-26", "time_et": "15:00",
        "home": "Senegal", "away": "Iraq",
        "venue": "BMO Field", "city": "Toronto",
    },

    # ── GROUP J ──────────────────────────────────────────────────────────────
    {
        # 00:00 ET Jun 17 = 9 pm PT Jun 16 — evening kickoff at a Santa Clara venue
        "match_id": 55, "stage": "Group Stage", "group": "J",
        "date": "2026-06-17", "time_et": "00:00",
        "home": "Austria", "away": "Jordan",
        "venue": "Levi's Stadium", "city": "Santa Clara",
    },
    {
        "match_id": 56, "stage": "Group Stage", "group": "J",
        "date": "2026-06-16", "time_et": "21:00",
        "home": "Argentina", "away": "Algeria",
        "venue": "Arrowhead Stadium", "city": "Kansas City",
    },
    {
        "match_id": 57, "stage": "Group Stage", "group": "J",
        "date": "2026-06-22", "time_et": "13:00",
        "home": "Argentina", "away": "Austria",
        "venue": "AT&T Stadium", "city": "Arlington",
    },
    {
        "match_id": 58, "stage": "Group Stage", "group": "J",
        "date": "2026-06-22", "time_et": "23:00",
        "home": "Jordan", "away": "Algeria",
        "venue": "Levi's Stadium", "city": "Santa Clara",
    },
    {
        "match_id": 59, "stage": "Group Stage", "group": "J",
        "date": "2026-06-27", "time_et": "22:00",
        "home": "Jordan", "away": "Argentina",
        "venue": "AT&T Stadium", "city": "Arlington",
    },
    {
        "match_id": 60, "stage": "Group Stage", "group": "J",
        "date": "2026-06-27", "time_et": "22:00",
        "home": "Algeria", "away": "Austria",
        "venue": "Arrowhead Stadium", "city": "Kansas City",
    },

    # ── GROUP K ──────────────────────────────────────────────────────────────
    {
        "match_id": 61, "stage": "Group Stage", "group": "K",
        "date": "2026-06-17", "time_et": "13:00",
        "home": "Portugal", "away": "DR Congo",
        "venue": "NRG Stadium", "city": "Houston",
    },
    {
        "match_id": 62, "stage": "Group Stage", "group": "K",
        "date": "2026-06-17", "time_et": "22:00",
        "home": "Uzbekistan", "away": "Colombia",
        "venue": "Estadio Azteca", "city": "Mexico City",
    },
    {
        "match_id": 63, "stage": "Group Stage", "group": "K",
        "date": "2026-06-23", "time_et": "13:00",
        "home": "Portugal", "away": "Uzbekistan",
        "venue": "NRG Stadium", "city": "Houston",
    },
    {
        "match_id": 64, "stage": "Group Stage", "group": "K",
        "date": "2026-06-23", "time_et": "22:00",
        "home": "Colombia", "away": "DR Congo",
        "venue": "Estadio Akron", "city": "Zapopan",
    },
    {
        "match_id": 65, "stage": "Group Stage", "group": "K",
        "date": "2026-06-27", "time_et": "19:30",
        "home": "Colombia", "away": "Portugal",
        "venue": "Hard Rock Stadium", "city": "Miami Gardens",
    },
    {
        "match_id": 66, "stage": "Group Stage", "group": "K",
        "date": "2026-06-27", "time_et": "19:30",
        "home": "DR Congo", "away": "Uzbekistan",
        "venue": "Mercedes-Benz Stadium", "city": "Atlanta",
    },

    # ── GROUP L ──────────────────────────────────────────────────────────────
    {
        "match_id": 67, "stage": "Group Stage", "group": "L",
        "date": "2026-06-17", "time_et": "16:00",
        "home": "England", "away": "Croatia",
        "venue": "AT&T Stadium", "city": "Arlington",
    },
    {
        "match_id": 68, "stage": "Group Stage", "group": "L",
        "date": "2026-06-17", "time_et": "19:00",
        "home": "Ghana", "away": "Panama",
        "venue": "BMO Field", "city": "Toronto",
    },
    {
        "match_id": 69, "stage": "Group Stage", "group": "L",
        "date": "2026-06-23", "time_et": "16:00",
        "home": "England", "away": "Ghana",
        "venue": "Gillette Stadium", "city": "Foxborough",
    },
    {
        "match_id": 70, "stage": "Group Stage", "group": "L",
        "date": "2026-06-23", "time_et": "19:00",
        "home": "Panama", "away": "Croatia",
        "venue": "BMO Field", "city": "Toronto",
    },
    {
        "match_id": 71, "stage": "Group Stage", "group": "L",
        "date": "2026-06-27", "time_et": "17:00",
        "home": "Panama", "away": "England",
        "venue": "MetLife Stadium", "city": "East Rutherford",
    },
    {
        "match_id": 72, "stage": "Group Stage", "group": "L",
        "date": "2026-06-27", "time_et": "17:00",
        "home": "Croatia", "away": "Ghana",
        "venue": "Lincoln Financial Field", "city": "Philadelphia",
    },

    # ── ROUND OF 32 ──────────────────────────────────────────────────────────
    # Bracket determined by group results. Specific kick-off times not yet set.
    # "Best 3rd (X/Y/…)" slots are awarded to the best-performing third-placed
    # teams from those groups (determined after group stage concludes).
    {
        "match_id": 73, "stage": "Round of 32", "group": None,
        "date": "2026-06-28", "time_et": "TBD",
        "home": "Runner-up Group A", "away": "Runner-up Group B",
        "venue": "SoFi Stadium", "city": "Inglewood",
    },
    {
        "match_id": 74, "stage": "Round of 32", "group": None,
        "date": "2026-06-29", "time_et": "TBD",
        "home": "Winner Group E", "away": "Best 3rd (A/B/C/D/F)",
        "venue": "Gillette Stadium", "city": "Foxborough",
    },
    {
        "match_id": 75, "stage": "Round of 32", "group": None,
        "date": "2026-06-29", "time_et": "TBD",
        "home": "Winner Group F", "away": "Runner-up Group C",
        "venue": "Estadio BBVA", "city": "Guadalupe",
    },
    {
        "match_id": 76, "stage": "Round of 32", "group": None,
        "date": "2026-06-29", "time_et": "TBD",
        "home": "Winner Group C", "away": "Runner-up Group F",
        "venue": "NRG Stadium", "city": "Houston",
    },
    {
        "match_id": 77, "stage": "Round of 32", "group": None,
        "date": "2026-06-30", "time_et": "TBD",
        "home": "Winner Group I", "away": "Best 3rd (C/D/F/G/H)",
        "venue": "MetLife Stadium", "city": "East Rutherford",
    },
    {
        "match_id": 78, "stage": "Round of 32", "group": None,
        "date": "2026-06-30", "time_et": "TBD",
        "home": "Runner-up Group E", "away": "Runner-up Group I",
        "venue": "AT&T Stadium", "city": "Arlington",
    },
    {
        "match_id": 79, "stage": "Round of 32", "group": None,
        "date": "2026-06-30", "time_et": "TBD",
        "home": "Winner Group A", "away": "Best 3rd (C/E/F/H/I)",
        "venue": "Estadio Azteca", "city": "Mexico City",
    },
    {
        "match_id": 80, "stage": "Round of 32", "group": None,
        "date": "2026-07-01", "time_et": "TBD",
        "home": "Winner Group L", "away": "Best 3rd (E/H/I/J/K)",
        "venue": "Mercedes-Benz Stadium", "city": "Atlanta",
    },
    {
        "match_id": 81, "stage": "Round of 32", "group": None,
        "date": "2026-07-01", "time_et": "TBD",
        "home": "Winner Group D", "away": "Best 3rd (B/E/F/I/J)",
        "venue": "Levi's Stadium", "city": "Santa Clara",
    },
    {
        "match_id": 82, "stage": "Round of 32", "group": None,
        "date": "2026-07-01", "time_et": "TBD",
        "home": "Winner Group G", "away": "Best 3rd (A/E/H/I/J)",
        "venue": "Lumen Field", "city": "Seattle",
    },
    {
        "match_id": 83, "stage": "Round of 32", "group": None,
        "date": "2026-07-02", "time_et": "TBD",
        "home": "Runner-up Group K", "away": "Runner-up Group L",
        "venue": "BMO Field", "city": "Toronto",
    },
    {
        "match_id": 84, "stage": "Round of 32", "group": None,
        "date": "2026-07-02", "time_et": "TBD",
        "home": "Winner Group H", "away": "Runner-up Group J",
        "venue": "SoFi Stadium", "city": "Inglewood",
    },
    {
        "match_id": 85, "stage": "Round of 32", "group": None,
        "date": "2026-07-02", "time_et": "TBD",
        "home": "Winner Group B", "away": "Best 3rd (E/F/G/I/J)",
        "venue": "BC Place", "city": "Vancouver",
    },
    {
        "match_id": 86, "stage": "Round of 32", "group": None,
        "date": "2026-07-03", "time_et": "TBD",
        "home": "Winner Group J", "away": "Runner-up Group H",
        "venue": "Hard Rock Stadium", "city": "Miami Gardens",
    },
    {
        "match_id": 87, "stage": "Round of 32", "group": None,
        "date": "2026-07-03", "time_et": "TBD",
        "home": "Winner Group K", "away": "Best 3rd (D/E/I/J/L)",
        "venue": "Arrowhead Stadium", "city": "Kansas City",
    },
    {
        "match_id": 88, "stage": "Round of 32", "group": None,
        "date": "2026-07-03", "time_et": "TBD",
        "home": "Runner-up Group D", "away": "Runner-up Group G",
        "venue": "AT&T Stadium", "city": "Arlington",
    },

    # ── ROUND OF 16 ──────────────────────────────────────────────────────────
    # home/away reference match IDs from the Round of 32 above.
    {
        "match_id": 89, "stage": "Round of 16", "group": None,
        "date": "2026-07-04", "time_et": "TBD",
        "home": "Winner Match 74", "away": "Winner Match 77",
        "venue": "Lincoln Financial Field", "city": "Philadelphia",
    },
    {
        "match_id": 90, "stage": "Round of 16", "group": None,
        "date": "2026-07-04", "time_et": "TBD",
        "home": "Winner Match 73", "away": "Winner Match 75",
        "venue": "NRG Stadium", "city": "Houston",
    },
    {
        "match_id": 91, "stage": "Round of 16", "group": None,
        "date": "2026-07-05", "time_et": "TBD",
        "home": "Winner Match 76", "away": "Winner Match 78",
        "venue": "MetLife Stadium", "city": "East Rutherford",
    },
    {
        "match_id": 92, "stage": "Round of 16", "group": None,
        "date": "2026-07-05", "time_et": "TBD",
        "home": "Winner Match 79", "away": "Winner Match 80",
        "venue": "Estadio Azteca", "city": "Mexico City",
    },
    {
        "match_id": 93, "stage": "Round of 16", "group": None,
        "date": "2026-07-06", "time_et": "TBD",
        "home": "Winner Match 83", "away": "Winner Match 84",
        "venue": "AT&T Stadium", "city": "Arlington",
    },
    {
        "match_id": 94, "stage": "Round of 16", "group": None,
        "date": "2026-07-06", "time_et": "TBD",
        "home": "Winner Match 81", "away": "Winner Match 82",
        "venue": "Lumen Field", "city": "Seattle",
    },
    {
        "match_id": 95, "stage": "Round of 16", "group": None,
        "date": "2026-07-07", "time_et": "TBD",
        "home": "Winner Match 86", "away": "Winner Match 88",
        "venue": "Mercedes-Benz Stadium", "city": "Atlanta",
    },
    {
        "match_id": 96, "stage": "Round of 16", "group": None,
        "date": "2026-07-07", "time_et": "TBD",
        "home": "Winner Match 85", "away": "Winner Match 87",
        "venue": "BC Place", "city": "Vancouver",
    },

    # ── QUARTERFINALS ────────────────────────────────────────────────────────
    {
        "match_id": 97, "stage": "Quarterfinal", "group": None,
        "date": "2026-07-09", "time_et": "TBD",
        "home": "Winner Match 89", "away": "Winner Match 90",
        "venue": "Gillette Stadium", "city": "Foxborough",
    },
    {
        "match_id": 98, "stage": "Quarterfinal", "group": None,
        "date": "2026-07-10", "time_et": "TBD",
        "home": "Winner Match 93", "away": "Winner Match 94",
        "venue": "SoFi Stadium", "city": "Inglewood",
    },
    {
        "match_id": 99, "stage": "Quarterfinal", "group": None,
        "date": "2026-07-11", "time_et": "TBD",
        "home": "Winner Match 91", "away": "Winner Match 92",
        "venue": "Hard Rock Stadium", "city": "Miami Gardens",
    },
    {
        "match_id": 100, "stage": "Quarterfinal", "group": None,
        "date": "2026-07-11", "time_et": "TBD",
        "home": "Winner Match 95", "away": "Winner Match 96",
        "venue": "Arrowhead Stadium", "city": "Kansas City",
    },

    # ── SEMIFINALS ───────────────────────────────────────────────────────────
    {
        "match_id": 101, "stage": "Semifinal", "group": None,
        "date": "2026-07-14", "time_et": "TBD",
        "home": "Winner Match 97", "away": "Winner Match 98",
        "venue": "AT&T Stadium", "city": "Arlington",
    },
    {
        "match_id": 102, "stage": "Semifinal", "group": None,
        "date": "2026-07-15", "time_et": "TBD",
        "home": "Winner Match 99", "away": "Winner Match 100",
        "venue": "Mercedes-Benz Stadium", "city": "Atlanta",
    },

    # ── THIRD PLACE PLAYOFF ──────────────────────────────────────────────────
    {
        "match_id": 103, "stage": "Third Place Playoff", "group": None,
        "date": "2026-07-18", "time_et": "TBD",
        "home": "Loser Match 101", "away": "Loser Match 102",
        "venue": "Hard Rock Stadium", "city": "Miami Gardens",
    },

    # ── FINAL ────────────────────────────────────────────────────────────────
    {
        "match_id": 104, "stage": "Final", "group": None,
        "date": "2026-07-19", "time_et": "TBD",
        "home": "Winner Match 101", "away": "Winner Match 102",
        "venue": "MetLife Stadium", "city": "East Rutherford",
    },
]

# ── Convenience lookups ──────────────────────────────────────────────────────

FIXTURE_BY_ID: dict[int, Fixture] = {f["match_id"]: f for f in FIXTURES}

GROUP_STAGE_FIXTURES: list[Fixture] = [f for f in FIXTURES if f["group"] is not None]

KNOCKOUT_FIXTURES: list[Fixture] = [f for f in FIXTURES if f["group"] is None]

STAGE_ORDER: list[str] = [
    "Group Stage",
    "Round of 32",
    "Round of 16",
    "Quarterfinal",
    "Semifinal",
    "Third Place Playoff",
    "Final",
]

# Team → list of their match IDs (group stage only)
TEAM_FIXTURES: dict[str, list[int]] = {}
for _fixture in GROUP_STAGE_FIXTURES:
    for _team in (_fixture["home"], _fixture["away"]):
        TEAM_FIXTURES.setdefault(_team, []).append(_fixture["match_id"])
