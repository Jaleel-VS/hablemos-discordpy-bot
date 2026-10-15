"""Fixed-point helpers for the Outpost engine (see plans/outpost.md §7.6).

All combat math is integer-only; ``Q = 10**9`` is the unit of fractions.
"""

import math

Q: int = 10**9  # fixed-point denominator; fractions are ints in [0, Q]


def pow15(n: int, d: int) -> int:
    """Return ``(n/d)^1.5`` in fixed point (result in ``[0, Q]``).

    Implements ``r * isqrt(r*Q) // Q`` with ``r = n*Q//d`` as specified
    in plans/outpost.md §6.7.  Caller must ensure ``d > 0``.
    """
    r = n * Q // d
    return r * math.isqrt(r * Q) // Q
