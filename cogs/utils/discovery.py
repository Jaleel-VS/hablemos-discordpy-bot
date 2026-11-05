"""Shared cog discovery utility."""
import importlib
from pathlib import Path

COGS_DIR = Path(__file__).resolve().parent.parent


def discover_extensions() -> list[str]:
    """Return all discoverable cog extension paths (e.g. 'cogs.league_cog.main')."""
    return sorted(
        f"cogs.{d.parent.name}.{d.stem}"
        for d in COGS_DIR.glob("*_cog/main*.py")
    )


def is_code_enabled(ext: str) -> bool:
    """Return whether a cog's config enables it; missing config defaults to enabled."""
    config_module = ext.rsplit('.', 1)[0] + '.config'
    try:
        mod = importlib.import_module(config_module)
    except (ImportError, ModuleNotFoundError):
        return True
    return getattr(mod, 'ENABLED', True)
