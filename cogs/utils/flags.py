"""Random flag selection for Spanish- and English-speaking countries.

Rather than always showing 🇪🇸 / 🇬🇧, callers can use these helpers to
pick a flag from the full roster of major speaker nations — better
representation without any other logic change.
"""
import random

# Major Spanish-speaking countries by native speaker population.
SPANISH_FLAGS: tuple[str, ...] = (
    "🇲🇽",  # Mexico        ~130m
    "🇨🇴",  # Colombia       ~50m
    "🇪🇸",  # Spain          ~47m
    "🇦🇷",  # Argentina      ~45m
    "🇵🇪",  # Peru           ~32m
    "🇻🇪",  # Venezuela      ~29m
    "🇨🇱",  # Chile          ~19m
    "🇪🇨",  # Ecuador        ~17m
    "🇬🇹",  # Guatemala      ~17m
    "🇨🇺",  # Cuba           ~11m
    "🇧🇴",  # Bolivia        ~10m
    "🇩🇴",  # Dominican Rep  ~10m
    "🇭🇳",  # Honduras        ~9m
    "🇵🇾",  # Paraguay        ~7m
    "🇸🇻",  # El Salvador     ~6m
    "🇳🇮",  # Nicaragua       ~6m
    "🇨🇷",  # Costa Rica      ~5m
    "🇵🇦",  # Panama          ~4m
    "🇺🇾",  # Uruguay         ~3m
    "🇵🇷",  # Puerto Rico     ~3m
)

# Major English-speaking countries by native speaker population.
ENGLISH_FLAGS: tuple[str, ...] = (
    "🇺🇸",  # United States  ~310m
    "🇬🇧",  # United Kingdom  ~67m
    "🇨🇦",  # Canada          ~30m
    "🇦🇺",  # Australia       ~25m
    "🇳🇬",  # Nigeria         ~24m (largest English-speaking country in Africa)
    "🇵🇭",  # Philippines     ~14m
    "🇿🇦",  # South Africa    ~10m
    "🇬🇭",  # Ghana            ~8m
    "🇳🇿",  # New Zealand      ~5m
    "🇮🇪",  # Ireland          ~5m
    "🇯🇲",  # Jamaica          ~3m
    "🇸🇬",  # Singapore        ~2m
    "🇹🇹",  # Trinidad         ~1m
    "🇧🇧",  # Barbados        <1m
    "🇧🇿",  # Belize          <1m
)


def random_spanish_flag() -> str:
    """Return a randomly chosen flag from a major Spanish-speaking nation."""
    return random.choice(SPANISH_FLAGS)


def random_english_flag() -> str:
    """Return a randomly chosen flag from a major English-speaking nation."""
    return random.choice(ENGLISH_FLAGS)
