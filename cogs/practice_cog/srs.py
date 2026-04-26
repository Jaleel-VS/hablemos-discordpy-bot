"""
FSRS (Free Spaced Repetition Scheduler) wrapper.

Ratings:
- Again (1): Forgot the card
- Hard  (2): Remembered with serious difficulty
- Good  (3): Remembered after hesitation
- Easy  (4): Remembered easily
"""
from fsrs import Card, Rating, Scheduler

# Shared scheduler instance (stateless — safe to reuse)
scheduler = Scheduler()


def review_card(card_json: str | None, rating: Rating) -> tuple[str, str]:
    """Review a card and return (updated_card_json, due_iso).

    Args:
        card_json: Serialized FSRS Card JSON, or None for a new card.
        rating: FSRS Rating (Again, Hard, Good, Easy).

    Returns:
        Tuple of (card_json, due_iso_string).
    """
    card = Card.from_json(card_json) if card_json else Card()
    card, _log = scheduler.review_card(card, rating)
    return card.to_json(), card.due.isoformat()


# Re-export for views
RATING_AGAIN = Rating.Again
RATING_HARD = Rating.Hard
RATING_GOOD = Rating.Good
RATING_EASY = Rating.Easy
