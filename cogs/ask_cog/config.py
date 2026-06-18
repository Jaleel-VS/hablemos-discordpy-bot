"""Configuration for the Ask cog."""
from typing import Final

from config import get_str_env

# Gemini model used by `$ask`. Overridable via env so we can bump the
# model without a redeploy. Default tracks the current stable Flash
# model (see https://ai.google.dev/gemini-api/docs/models).
MODEL_NAME: Final[str] = get_str_env("GEMINI_ASK_MODEL", "gemini-3.5-flash")
