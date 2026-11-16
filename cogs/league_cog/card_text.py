"""Card text in the language a member is learning.

Spanish learners read their cards in Spanish and everyone else in English,
so the cards double as reading practice.
"""
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from cogs.utils.guild import LEARNING_ENGLISH_ROLE_ID, LEARNING_SPANISH_ROLE_ID


@dataclass(frozen=True)
class CardText:
    """Every string drawn on a league card, in one language."""

    level_up: str
    level: str
    to_next: str
    this_round: str
    ends_in: str
    board_spanish: str
    board_english: str
    combined: str
    score: str
    bonus: str
    active_days: str
    behind: str
    tied: str
    leading: str
    alone: str
    streak: str
    streak_one: str
    no_streak: str
    best_streak: str
    champion: str
    best_round: str
    last_7_days: str
    not_in_league: str
    tiers: dict[str, str]

    def tier(self, name: str) -> str:
        return self.tiers.get(name, name)

    def ends(self, days: int, hours: int) -> str:
        """``ends_in`` with a compact duration, e.g. ``2d 5h``."""
        span = f"{days}d {hours}h" if days else f"{hours}h"
        return self.ends_in.format(span=span)

    def streak_line(self, days: int, best: int) -> str:
        """Current streak and best streak, e.g. ``5-day streak · best 12``."""
        current = (self.no_streak if days == 0
                   else self.streak_one if days == 1
                   else self.streak.format(days=days))
        return f"{current}  ·  {self.best_streak.format(days=best)}"


EN = CardText(
    level_up="LEVEL UP",
    level="Level {level}",
    to_next="{points:,} pts to level {level}",
    this_round="THIS ROUND",
    ends_in="ENDS IN {span}",
    board_spanish="Spanish",
    board_english="English",
    combined="Combined",
    score="Score",
    bonus="{points:,} pts + {bonus:,} bonus",
    active_days="Active days",
    behind="{points:,} pts behind #{rank}",
    tied="Tied on points with #{rank}",
    leading="Leading by {points:,} pts",
    alone="Top of the board",
    streak="{days}-day streak",
    streak_one="1-day streak",
    no_streak="No active streak",
    best_streak="best {days}",
    champion="Champion",
    best_round="Best round",
    last_7_days="LAST 7 DAYS",
    not_in_league="Join the league with /league join to compete this round",
    tiers={},
)

ES = CardText(
    level_up="¡SUBISTE DE NIVEL!",
    level="Nivel {level}",
    to_next="{points:,} pts para el nivel {level}",
    this_round="ESTA RONDA",
    ends_in="TERMINA EN {span}",
    board_spanish="Español",
    board_english="Inglés",
    combined="Combinada",
    score="Puntuación",
    bonus="{points:,} pts + {bonus:,} de bonus",
    active_days="Días activos",
    behind="A {points:,} pts del #{rank}",
    tied="Empatado en puntos con el #{rank}",
    leading="Primero por {points:,} pts",
    alone="Primero de la tabla",
    streak="Racha de {days} días",
    streak_one="Racha de 1 día",
    no_streak="Sin racha activa",
    best_streak="récord {days}",
    champion="Campeón",
    best_round="Mejor ronda",
    last_7_days="ÚLTIMOS 7 DÍAS",
    not_in_league="Únete a la liga con /league join para competir esta ronda",
    tiers={
        "Dawn": "Alba",
        "Mist": "Bruma",
        "Lilac": "Lila",
        "Tide": "Marea",
        "Bloom": "Flor",
        "Gold": "Oro",
    },
)


def card_text_for(role_ids: Collection[int]) -> CardText:
    """Spanish for members learning Spanish (and not English); English otherwise."""
    if LEARNING_SPANISH_ROLE_ID in role_ids and LEARNING_ENGLISH_ROLE_ID not in role_ids:
        return ES
    return EN
