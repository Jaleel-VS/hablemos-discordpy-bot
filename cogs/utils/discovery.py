"""Shared cog discovery utility."""
from pathlib import Path

COGS_DIR = Path(__file__).resolve().parent.parent


def discover_extensions() -> list[str]:
    """Return all discoverable cog extension paths (e.g. 'cogs.league_cog.main')."""
    return sorted(
        f"cogs.{d.parent.name}.{d.stem}"
        for d in COGS_DIR.glob("*_cog/main*.py")
    )
