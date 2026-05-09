"""Render the league's top-activity channels as a horizontal bar chart.

Owner-only admin visualization. Callers pass the raw rows from
``db.get_top_activity_channels``, pre-resolved channel labels, and the
set of currently-excluded channel IDs so the chart can visually mark
them.
"""
from __future__ import annotations

import logging
from io import BytesIO

from cogs.utils.plotting import configure_backend

logger = logging.getLogger(__name__)

# Colors tuned for Discord dark-theme embeds.
_BAR_COLOR = "#5865F2"          # Discord blurple
_BAR_EXCLUDED_COLOR = "#ED4245"  # Discord red — currently excluded channels
_TEXT_COLOR = "#2b2d31"
_FACE_COLOR = "white"


def render_top_channels(
    rows: list[dict],
    *,
    channel_labels: dict[int, str],
    excluded_ids: set[int],
    days: int,
) -> BytesIO:
    """Render top-N channels by message count as a horizontal bar chart.

    Args:
        rows: Rows from ``get_top_activity_channels`` — each has
            ``channel_id``, ``msg_count``, ``unique_users``. The caller
            orders them most-active first; we preserve that order.
        channel_labels: Mapping from ``channel_id`` → human label
            (typically ``#channel-name``; fall back to ``#<id>`` when
            the channel is uncached or deleted).
        excluded_ids: Channel IDs currently excluded from league
            tracking. Those bars are colored red to surface "used to be
            a top channel, now disabled" cases at a glance.
        days: Size of the lookback window, used only for the title.

    Returns:
        A ``BytesIO`` positioned at 0, ready for ``discord.File``.
    """
    configure_backend()

    import matplotlib.pyplot as plt

    # Reverse so the most-active channel appears at the top of the chart
    # (matplotlib's barh draws bottom-up by default).
    rows = list(reversed(rows))

    labels = [channel_labels.get(r["channel_id"], f"#{r['channel_id']}") for r in rows]
    counts = [int(r["msg_count"]) for r in rows]
    users = [int(r["unique_users"]) for r in rows]
    colors = [
        _BAR_EXCLUDED_COLOR if r["channel_id"] in excluded_ids else _BAR_COLOR
        for r in rows
    ]

    total = sum(counts) or 1  # prevent div-by-zero on empty input

    # Figure height scales with number of rows so bars don't look squashed
    # when there are 15 channels but stay readable with just 3-4.
    fig_height = max(3.2, 0.45 * len(rows) + 1.2)
    fig, ax = plt.subplots(
        figsize=(11, fig_height), dpi=150, constrained_layout=True,
    )

    bars = ax.barh(labels, counts, color=colors, edgecolor=_TEXT_COLOR, linewidth=0.5)

    # Right-side annotation: exact count · unique users · share of total.
    max_count = max(counts) if counts else 1
    for bar, n, u in zip(bars, counts, users, strict=True):
        share = n / total * 100
        ax.text(
            bar.get_width() + max_count * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{n:,}  ·  {u} users  ·  {share:.1f}%",
            va="center", ha="left", fontsize=9, color=_TEXT_COLOR,
        )

    # Leave headroom on the right for the annotations.
    ax.set_xlim(0, max_count * 1.28)

    ax.set_title(
        f"Top league channels — last {days} day(s)",
        fontsize=13, pad=10, color=_TEXT_COLOR,
    )
    ax.set_xlabel("Messages", fontsize=10, color=_TEXT_COLOR)
    ax.tick_params(axis="y", labelsize=9, colors=_TEXT_COLOR)
    ax.tick_params(axis="x", labelsize=8, colors=_TEXT_COLOR)

    # Cleaner spines — keep bottom + left only.
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    # Legend only when there's actually an excluded channel in view, so
    # we don't show a legend with a single entry on the happy path.
    if any(r["channel_id"] in excluded_ids for r in rows):
        from matplotlib.patches import Patch
        legend_handles = [
            Patch(facecolor=_BAR_COLOR, label="Active"),
            Patch(facecolor=_BAR_EXCLUDED_COLOR, label="Excluded"),
        ]
        ax.legend(
            handles=legend_handles, loc="lower right",
            frameon=False, fontsize=9,
        )

    buf = BytesIO()
    try:
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor=_FACE_COLOR)
    finally:
        plt.close(fig)

    buf.seek(0)
    return buf
