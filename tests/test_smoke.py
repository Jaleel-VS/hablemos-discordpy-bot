"""Import smoke tests.

Verify that every cog extension and every db mixin can be imported
without error.  This catches broken ``from x import y`` statements —
the kind that only blow up at bot startup — before they reach prod.

No Discord connection, no database, no env vars required: we import
the modules but never instantiate anything.

Skip conditions (pre-existing, not our bugs):
  ModuleNotFoundError — optional/prod-only package not installed locally
                        (e.g. aioboto3 for S3, wkhtmltopdf bindings)
  ValueError("... environment variable is required") — a config module
    calls get_required_env() at import time; unavoidable without the env.

Fail conditions (regressions we care about):
  ImportError that is NOT ModuleNotFoundError — e.g. "cannot import name
  'create_default_avatar' from '...'" caused by renaming a public symbol.
"""
import importlib
from pathlib import Path

import pytest

from cogs.utils.discovery import discover_extensions


def _db_modules() -> list[str]:
    return sorted(
        f"db.{p.stem}"
        for p in Path("db").glob("*.py")
        if p.stem not in ("__init__", "schema")
    )


def _try_import(module: str) -> None:
    try:
        importlib.import_module(module)
    except ModuleNotFoundError as e:
        # Optional or prod-only package not installed in dev.
        pytest.skip(f"optional dependency not installed: {e}")
    except ValueError as e:
        if "environment variable is required" in str(e):
            pytest.skip(f"required env var absent in test env: {e}")
        raise
    # Any other ImportError (e.g. "cannot import name 'X'") propagates
    # as a test failure — that's the class of bug we want to catch.


@pytest.mark.parametrize("module", discover_extensions())
def test_cog_importable(module: str) -> None:
    """Each discovered cog must be importable without error."""
    _try_import(module)


@pytest.mark.parametrize("module", _db_modules())
def test_db_mixin_importable(module: str) -> None:
    """Each DB mixin must be importable without error."""
    _try_import(module)
