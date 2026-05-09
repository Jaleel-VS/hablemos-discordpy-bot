"""Render the league activity heatmap as a PNG using seaborn.

The helper is deliberately self-contained and lazy-imports matplotlib
and seaborn on first call so the bot's cold-start isn't paying for
plotting libraries that are only touched by an owner-only admin command.

Why a dedicated module:

* Keeps ``admin.py`` focused on command wiring; drawing lives here.
* Ensures the Agg backend is configured *before* ``matplotlib.pyplot``
  is imported anywhere in the process (required for headless
  containers; setting it after pyplot is a no-op on most backends).
* Gives us one place to tweak colors, DPI, and labels as the bot's
  visual style evolves.
"""
from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)

# Matplotlib is imported lazily inside render_heatmap(). The first call
# pays the ~1 s import cost; subsequent calls reuse the loaded modules.
_BACKEND_CONFIGURED = False


def _configure_backend() -> None:
    """Force the non-interactive Agg backend exactly once.

    Must run before ``matplotlib.pyplot`` is imported anywhere in the
    process. Safe to call repeatedly — the ``force=True`` flag makes
    matplotlib swap backends even if one was already selected, and the
    module-level guard keeps the work to a single call.
    """
    global _BACKEND_CONFIGURED
    if _BACKEND_CONFIGURED:
        return
    import matplotlib
    matplotlib.use("Agg", force=True)
    _BACKEND_CONFIGURED = True


# Day-of-week layout: Postgres' DOW is 0=Sun..6=Sat; humans read Mon-first.
_DOW_ORDER = [1, 2, 3, 4, 5, 6, 0]
_DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def render_heatmap(
    grid: list[list[int]],
    *,
    days: int,
    peak: int,
) -> BytesIO:
    """Render a 7x24 activity heatmap to a PNG in memory.

    Args:
        grid: 7x24 matrix indexed as ``grid[dow][hour]`` where ``dow``
            follows Postgres' convention (0=Sunday..6=Saturday) and
            ``hour`` is 0-23 UTC.
        days: Size of the lookback window, used only for the title.
        peak: Maximum cell value. Passed in so the caller can early-exit
            on an empty window without calling us at all; here it just
            tunes the annotation format.

    Returns:
        A ``BytesIO`` positioned at 0, ready to hand to ``discord.File``.
    """
    _configure_backend()

    # Lazy-import after backend selection so pyplot picks up Agg.
    import matplotlib.pyplot as plt
    import pandas as pd
    import seaborn as sns

    # Reorder rows Mon..Sun and label axes via a DataFrame so seaborn
    # picks up tick labels for free.
    reordered = [grid[dow] for dow in _DOW_ORDER]
    df = pd.DataFrame(
        reordered,
        index=_DOW_LABELS,
        columns=[f"{h:02d}" for h in range(24)],
    )

    # Integer annotations look cleaner than the default .2g float format
    # for count data. Hide zeros — a 7x24 board full of "0"s is noisy.
    annot = df.map(lambda v: str(v) if v > 0 else "")

    # Figure sized for Discord embeds: ~1400px wide at 150 DPI reads
    # well on both desktop and mobile without being huge in the channel.
    fig, ax = plt.subplots(figsize=(12, 4.5), dpi=150, constrained_layout=True)

    sns.heatmap(
        df,
        ax=ax,
        cmap="rocket_r",
        annot=annot,
        fmt="",                # annot is already pre-formatted strings
        annot_kws={"size": 8},
        linewidths=0.3,
        linecolor="#2b2d31",   # matches Discord dark-theme background
        cbar_kws={"label": "messages", "shrink": 0.8},
        square=False,
        xticklabels=True,
        yticklabels=True,
    )

    ax.set_title(
        f"League activity — last {days} day(s), peak = {peak:,}",
        fontsize=12, pad=10,
    )
    ax.set_xlabel("Hour (UTC)", fontsize=10)
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=0, labelsize=8)
    ax.tick_params(axis="y", rotation=0, labelsize=9)

    buf = BytesIO()
    try:
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    finally:
        # Always close the figure — leaked figures accumulate in
        # matplotlib's global registry and eat memory fast.
        plt.close(fig)

    buf.seek(0)
    return buf
