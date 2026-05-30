"""Pure scoring helpers for World Cup predictions.

Kept free of Discord/DB types so it can be exercised in isolation.
"""

# Points awarded for picking the eventual champion correctly.
POINTS_CORRECT_WINNER = 1


def score_prediction(predicted_role_id: int | None, winner_role_id: int | None) -> int:
    """Return points for a single prediction.

    Returns 0 when either side is missing so the call site can defer
    grading until the admin records a champion.
    """
    if predicted_role_id is None or winner_role_id is None:
        return 0
    return POINTS_CORRECT_WINNER if predicted_role_id == winner_role_id else 0
