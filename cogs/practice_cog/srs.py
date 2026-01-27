"""
SM-2 Spaced Repetition Algorithm

Quality ratings:
- 1 (Again): Failed - reset interval
- 3 (Hard): Correct but difficult
- 4 (Good): Correct with some hesitation
- 5 (Easy): Perfect recall
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class SRSResult:
    """Result of SM-2 calculation"""
    interval_days: float
    ease_factor: float
    repetitions: int
    next_review: datetime


def calculate_sm2(quality: int, interval_days: float, ease_factor: float,
                  repetitions: int) -> SRSResult:
    """
    Calculate new SRS values based on quality rating.

    Args:
        quality: Rating 1-5 (1=Again, 3=Hard, 4=Good, 5=Easy)
        interval_days: Current interval in days
        ease_factor: Current ease factor (typically 1.3-2.5)
        repetitions: Number of successful repetitions

    Returns:
        SRSResult with new values
    """
    # Clamp quality to valid range
    quality = max(1, min(5, quality))

    if quality < 3:
        # Failed - reset to beginning
        new_interval = 1.0
        new_repetitions = 0
        # Reduce ease factor but keep minimum of 1.3
        new_ease = max(1.3, ease_factor - 0.2)
    else:
        # Passed
        if repetitions == 0:
            new_interval = 1.0
        elif repetitions == 1:
            new_interval = 6.0
        else:
            new_interval = interval_days * ease_factor

        new_repetitions = repetitions + 1

        # Adjust ease factor based on quality
        # EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        new_ease = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ease = max(1.3, new_ease)  # Minimum 1.3

    # Calculate next review datetime
    now = datetime.now(timezone.utc)
    next_review = now + timedelta(days=new_interval)

    return SRSResult(
        interval_days=new_interval,
        ease_factor=new_ease,
        repetitions=new_repetitions,
        next_review=next_review
    )


# Quality rating constants for readability
QUALITY_AGAIN = 1
QUALITY_HARD = 3
QUALITY_GOOD = 4
QUALITY_EASY = 5
