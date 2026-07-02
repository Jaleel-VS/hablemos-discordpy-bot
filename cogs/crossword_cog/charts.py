"""Chart helpers for the crossword cog.

Currently exposes one renderer for the word-difficulty scatter. Kept as
a dedicated module (rather than extending ``renderer.py``) because the
rendering stack is matplotlib/seaborn, not Pillow — different dependency
profile, different lazy-import pattern.
"""
from __future__ import annotations

import logging
from io import BytesIO
from typing import cast

from cogs.utils.plotting import configure_backend

logger = logging.getLogger(__name__)

# How many points to label by name. Labeling everything turns the chart
# into a wall of overlapping text; labeling only the extremes (lowest
# solve rate, highest solve rate, slowest solves) surfaces the
# interesting cases.
_MAX_LABELED_POINTS = 10


def render_word_difficulty(
    rows: list[dict],
    *,
    language: str | None,
    days: int | None,
) -> BytesIO:
    """Scatter per-word solve rate vs average solve time.

    X axis: average seconds to solve (among successful solves).
    Y axis: solve rate (% of appearances that were solved).
    Point size: number of appearances (confidence proxy).
    Point color: difficulty bucket (beginner / advanced).

    Quadrant reading:
      * top-left:  solved often, solved fast      — likely too easy.
      * top-right: solved often, takes a while    — healthy "hard but fair".
      * bottom-left:  rarely solved, quickly      — clue probably broken.
      * bottom-right: rarely solved, slowly       — genuinely hard words.

    Args:
        rows: Rows from ``crossword_get_word_difficulty``. Each must
            carry ``word``, ``difficulty``, ``appearances``,
            ``solve_rate`` (0..1), and ``avg_solve_seconds`` (may be
            ``None`` for words that were never solved successfully).
        language: Filter label for the title ("es" / "en" / None).
        days: Lookback window in days, or None for all-time.

    Returns:
        A ``BytesIO`` positioned at 0.
    """
    configure_backend()

    import matplotlib.pyplot as plt
    import pandas as pd
    import seaborn as sns

    # Drop rows with no successful solves — they'd have no x-axis value
    # and silently disappear in scatter plots anyway. Surface that as a
    # footnote in the caller if needed.
    clean = [r for r in rows if r.get("avg_solve_seconds") is not None]
    if not clean:
        # Still return a valid PNG so the caller can just send it.
        fig, ax = plt.subplots(figsize=(8, 3), dpi=150, constrained_layout=True)
        ax.text(
            0.5, 0.5,
            "No solved words yet in this window.",
            ha="center", va="center", fontsize=12, color="#555",
        )
        ax.set_axis_off()
        buf = BytesIO()
        try:
            fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
        finally:
            plt.close(fig)
        buf.seek(0)
        return buf

    df = pd.DataFrame(
        {
            "word": [r["word"] for r in clean],
            "difficulty": [r["difficulty"] for r in clean],
            "language": [r["language"] for r in clean],
            "appearances": [int(r["appearances"]) for r in clean],
            "solve_rate_pct": [float(r["solve_rate"]) * 100 for r in clean],
            "avg_solve_seconds": [float(r["avg_solve_seconds"]) for r in clean],
        }
    )

    sns.set_theme(style="whitegrid", context="notebook")

    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=150, constrained_layout=True)

    sns.scatterplot(
        data=df,
        x="avg_solve_seconds",
        y="solve_rate_pct",
        size="appearances",
        sizes=(40, 360),
        hue="difficulty",
        palette={"beginner": "#57F287", "advanced": "#ED4245"},
        alpha=0.8,
        edgecolor="#2b2d31",
        linewidth=0.5,
        ax=ax,
    )

    # Annotate the N most "interesting" points: hardest, easiest, and
    # slowest (each bucket contributes a few). Dedup by word so a word
    # that's both "hardest" and "slowest" is only labeled once.
    interesting: list[int] = []
    # pandas-stubs types ``df[str]`` as ``Series | DataFrame``; these columns
    # are always Series, so cast to pick the Series ``.nsmallest``/``.nlargest``
    # overloads (which return a Series with a usable ``.index``).
    solve_rate = cast("pd.Series", df["solve_rate_pct"])
    avg_seconds = cast("pd.Series", df["avg_solve_seconds"])
    interesting += solve_rate.nsmallest(4).index.tolist()
    interesting += solve_rate.nlargest(3).index.tolist()
    interesting += avg_seconds.nlargest(3).index.tolist()
    seen: set[int] = set()
    ordered_unique: list[int] = []
    for i in interesting:
        if i not in seen:
            ordered_unique.append(i)
            seen.add(i)
        if len(ordered_unique) >= _MAX_LABELED_POINTS:
            break

    for i in ordered_unique:
        row = df.iloc[i]
        ax.annotate(
            row["word"],
            xy=(row["avg_solve_seconds"], row["solve_rate_pct"]),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=9,
            color="#2b2d31",
            fontweight="medium",
        )

    # Axis cosmetics.
    ax.set_ylim(-5, 105)
    ax.set_xlabel("Avg seconds to solve (successful solves only)", fontsize=10)
    ax.set_ylabel("Solve rate (%)", fontsize=10)
    from matplotlib.ticker import FuncFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}%"))

    # 50% reference line — helps eyeball "below-average difficulty".
    ax.axhline(50, color="#999", linestyle="--", linewidth=0.8, alpha=0.6)

    scope: list[str] = []
    if language:
        scope.append({"es": "Spanish", "en": "English"}.get(language, language))
    scope.append(f"last {days} day(s)" if days else "all time")
    ax.set_title(
        "Crossword word difficulty — " + " · ".join(scope),
        fontsize=13, pad=10,
    )

    # Seaborn renders the size legend + hue legend as one combined
    # legend; position it outside the plot so it doesn't obscure points.
    sns.move_legend(
        ax, "upper left",
        bbox_to_anchor=(1.01, 1.0),
        frameon=False,
        fontsize=9,
        title_fontsize=10,
    )

    buf = BytesIO()
    try:
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    finally:
        plt.close(fig)

    buf.seek(0)
    return buf
