"""Errors raised by the ``cogs.utils.gemini`` deep module.

This module owns the mapping from Gemini SDK errors to user-facing
strings. Cogs catch :class:`GeminiError` and surface ``.user_message``
directly.
"""
from google.genai import errors as genai_errors


class GeminiError(Exception):
    """Raised when a Gemini call fails after the ``Gemini.run`` pipeline.

    Attributes:
        code: HTTP status from the API (0 if the failure is not API-sourced).
        message: Raw error message from the API. Suitable for logs, not users.
        user_message: User-facing string. Already translated/formatted —
            cogs should send this directly to the user.
    """

    def __init__(self, code: int, message: str, user_message: str):
        super().__init__(f"{code} {message}")
        self.code = code
        self.message = message
        self.user_message = user_message


def user_message_for(err: genai_errors.APIError) -> str:
    """Map a Gemini ``APIError`` to a friendly user-facing message.

    The integer ``code`` is the HTTP status returned by the API. See
    https://googleapis.github.io/python-genai/ for the error hierarchy.
    """
    code = getattr(err, "code", None)
    if code == 400:
        return "Gemini rejected the request. Try rephrasing your question."
    if code in (401, 403):
        return "Gemini auth failed. The API key may be invalid or lack permission."
    if code == 404:
        return (
            "Configured Gemini model is unavailable. "
            "Check the `GEMINI_<feature>_MODEL` env var or `GEMINI_DEFAULT_MODEL`."
        )
    if code == 429:
        return "Rate limited by Gemini. Try again in a minute."
    if isinstance(code, int) and code >= 500:
        return "Gemini is having trouble right now. Please try again in a moment."
    msg = (getattr(err, "message", None) or "").lower()
    if any(k in msg for k in ("safety", "blocked")):
        return "Response blocked by content policy."
    return "Something went wrong talking to Gemini. Please try again later."
