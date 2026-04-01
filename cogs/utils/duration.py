"""Shared duration parsing utilities."""
import re
from datetime import timedelta

_DURATION_RE = re.compile(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?$", re.IGNORECASE)
MAX_DAYS = 90


def parse_duration(text: str, default: timedelta | None = None) -> timedelta:
    """Parse a duration string like ``7d``, ``12h``, or ``1d12h`` into a timedelta.

    A bare integer is treated as days for backwards compatibility.

    Raises ``ValueError`` on invalid input.
    """
    text = text.strip()

    # Bare integer → days
    if text.isdigit():
        return _clamp(timedelta(days=int(text)))

    m = _DURATION_RE.match(text)
    if not m or not any(m.groups()):
        if default is not None:
            return default
        raise ValueError(f"Invalid duration: `{text}`. Use e.g. `7d`, `12h`, `1d12h`.")

    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    return _clamp(timedelta(days=days, hours=hours, minutes=minutes))


def format_duration(td: timedelta) -> str:
    """Format a timedelta as a human-readable duration string."""
    total_seconds = int(td.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) or "0m"


def _clamp(td: timedelta) -> timedelta:
    if td <= timedelta(0):
        return timedelta(minutes=1)
    if td > timedelta(days=MAX_DAYS):
        return timedelta(days=MAX_DAYS)
    return td
