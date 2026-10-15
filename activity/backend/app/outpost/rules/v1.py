"""Ruleset v1: the static numbers from plans/outpost.md §6.2–6.4."""
from .model import (
    BuildingSpec,
    Params,
    Ruleset,
    TechSpec,
    UnitSpec,
    generate,
)

DEFAULT_PARAMS = Params()

BUILDINGS = (
    BuildingSpec("quarry", {"ore": 60, "wood": 15}, 1.5, 25),
    BuildingSpec("sawmill", {"ore": 48, "wood": 24}, 1.6, 25),
    BuildingSpec("gemworks", {"ore": 225, "wood": 75}, 1.5, 25, {"hall": 1}),
    BuildingSpec("farm", {"ore": 75, "wood": 30}, 1.5, 25),
    BuildingSpec("hall", {"ore": 200, "wood": 120, "gem": 60}, 1.75, 15),
    BuildingSpec("store", {"ore": 500, "wood": 250}, 1.8, 12),
    BuildingSpec("barracks", {"ore": 200, "wood": 100}, 1.6, 20, {"hall": 1}),
    BuildingSpec("wall", {"ore": 150, "wood": 200}, 1.6, 20, {"barracks": 1}),
    BuildingSpec(
        "tower", {"ore": 100, "wood": 150, "gem": 50}, 1.7, 10, {"hall": 3}
    ),
    BuildingSpec(
        "lab", {"ore": 200, "wood": 400, "gem": 200}, 1.8, 15, {"hall": 3}
    ),
)

# resource -> (producer building, per-level coefficient, flat base) (§6.2)
PRODUCTION = {
    "ore": ("quarry", 30, 30),
    "wood": ("sawmill", 25, 25),
    "gem": ("gemworks", 10, 5),
    "food": ("farm", 25, 20),
}

UNITS = (
    UnitSpec("warden", 1, {"ore": 50, "wood": 40}, 1, 10, "foot",
             40, 50, 6, 15, 180),
    UnitSpec("brute", 1, {"ore": 70, "wood": 30}, 1, 40, "foot",
             15, 10, 6, 40, 210),
    UnitSpec("scout", 1, {"ore": 40, "wood": 40, "gem": 10}, 1, 0, "-",
             2, 2, 18, 0, 120),
    UnitSpec("outrider", 2, {"ore": 120, "wood": 100, "gem": 20}, 2, 55,
             "swift", 20, 25, 14, 110, 420),
    UnitSpec("bulwark", 2, {"ore": 140, "wood": 160, "gem": 60}, 1, 10,
             "foot", 130, 110, 5, 0, 600),
    UnitSpec("lancer", 3, {"ore": 260, "wood": 180, "gem": 120}, 2, 200,
             "swift", 50, 30, 10, 60, 900),
    UnitSpec("hauler", 2, {"ore": 90, "wood": 110}, 1, 0, "-",
             5, 5, 9, 600, 300),
    UnitSpec("ram", 3, {"ore": 300, "wood": 400, "gem": 100}, 3, 30, "foot",
             30, 30, 4, 0, 1800),
    UnitSpec("settler", 3, {"ore": 4000, "wood": 4000, "gem": 2000}, 5, 0,
             "-", 10, 10, 5, 0, 7200),
)

TECHS = (
    TechSpec("arms", {"ore": 300, "wood": 500, "gem": 200}, 1.8, 10),
    TechSpec("armor", {"ore": 500, "wood": 300, "gem": 200}, 1.8, 10),
    TechSpec("logistics", {"ore": 400, "wood": 400, "gem": 100}, 1.8, 10),
    TechSpec("agronomy", {"ore": 300, "wood": 300, "gem": 100}, 1.8, 10),
    TechSpec("industry", {"ore": 500, "wood": 500, "gem": 250}, 1.8, 10),
    TechSpec("espionage", {"ore": 200, "wood": 300, "gem": 100}, 1.8, 10),
    TechSpec("charter", {"ore": 4000, "wood": 4000, "gem": 2000}, 3.0, 3),
)

# barracks level needed per unit tier (§6.2)
BARRACKS_TIER_LEVEL = {1: 1, 2: 5, 3: 10}


def build_ruleset(params: Params = DEFAULT_PARAMS) -> Ruleset:
    """Generate the v1 ruleset for the given params."""
    return generate(
        params, BUILDINGS, UNITS, TECHS, PRODUCTION, BARRACKS_TIER_LEVEL
    )
