"""Matplotlib graph renderers for the stats cog.

Each function returns a BytesIO PNG buffer ready to attach to a Discord message.
All rendering is CPU-bound and should be called via asyncio.to_thread().
"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from .config import ROLE_COLORS, ROLE_LABELS

# Consistent style
plt.style.use("dark_background")
FIGSIZE = (10, 6)
DPI = 100


def render_top_channels(
    data: list[dict], channel_names: dict[int, str], days: int
) -> io.BytesIO:
    """Horizontal bar chart of top channels by message count."""
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)

    channels = [channel_names.get(r["channel_id"], f"#{r['channel_id']}") for r in data]
    totals = [r["total"] for r in data]

    # Reverse for horizontal bar (top = highest)
    channels.reverse()
    totals.reverse()

    bars = ax.barh(channels, totals, color="#5865F2")
    ax.bar_label(bars, fmt="%d", padding=4)
    ax.set_xlabel("Messages")
    ax.set_title(f"Top Channels — Last {days} days")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return _fig_to_buffer(fig)


def render_role_daily(data: list[dict], days: int) -> io.BytesIO:
    """Stacked bar chart of daily messages by role type."""
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)

    # Pivot data: {day: {role_type: total}}
    days_map: dict[str, dict[str, int]] = {}
    for row in data:
        day_label = row["day"].strftime("%m/%d")
        if day_label not in days_map:
            days_map[day_label] = {}
        days_map[day_label][row["role_type"]] = row["total"]

    day_labels = list(days_map.keys())
    role_types = list(ROLE_LABELS.keys())

    bottom = np.zeros(len(day_labels))
    for role in role_types:
        values = [days_map.get(d, {}).get(role, 0) for d in day_labels]
        ax.bar(
            day_labels,
            values,
            bottom=bottom,
            label=ROLE_LABELS.get(role, role),
            color=ROLE_COLORS.get(role, "#888888"),
        )
        bottom += np.array(values)

    ax.set_xlabel("Date")
    ax.set_ylabel("Messages")
    ax.set_title(f"Daily Activity by Role — Last {days} days")
    ax.legend(loc="upper left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Rotate x labels if many days
    if len(day_labels) > 10:
        plt.xticks(rotation=45, ha="right")

    fig.tight_layout()
    return _fig_to_buffer(fig)


def render_growth(
    weekly_data: list[dict], total_users: int, mau: int
) -> io.BytesIO:
    """Dual-axis chart: new users per week (bar) + cumulative (line)."""
    fig, ax1 = plt.subplots(figsize=FIGSIZE, dpi=DPI)

    weeks = [r["week"].strftime("%m/%d") for r in weekly_data]
    new_users = [r["new_users"] for r in weekly_data]
    cumulative = []
    running = total_users - sum(new_users)
    for n in new_users:
        running += n
        cumulative.append(running)

    # Bars: new users per week
    ax1.bar(weeks, new_users, color="#5865F2", alpha=0.7, label="New users")
    ax1.set_xlabel("Week of")
    ax1.set_ylabel("New Users", color="#5865F2")
    ax1.tick_params(axis="y", labelcolor="#5865F2")

    # Line: cumulative
    ax2 = ax1.twinx()
    ax2.plot(weeks, cumulative, color="#FF6B6B", marker="o", linewidth=2, label="Total")
    ax2.set_ylabel("Total Users", color="#FF6B6B")
    ax2.tick_params(axis="y", labelcolor="#FF6B6B")

    ax1.set_title(f"User Growth (MAU: {mau:,})")
    ax1.spines["top"].set_visible(False)
    ax2.spines["top"].set_visible(False)

    if len(weeks) > 6:
        plt.xticks(rotation=45, ha="right")

    fig.tight_layout()
    return _fig_to_buffer(fig)


def render_heatmap(data: list[dict], days: int) -> io.BytesIO:
    """Hour × day-of-week activity heatmap."""
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)

    # Build 7x24 grid (dow × hour)
    grid = np.zeros((7, 24))
    for row in data:
        dow = int(row["dow"])
        hour = int(row["hour"])
        grid[dow][hour] = row["total"]

    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    im = ax.imshow(grid, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax.set_yticks(range(7))
    ax.set_yticklabels(day_names)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_xlabel("Hour (UTC)")
    ax.set_title(f"Activity Heatmap — Last {days} days")

    fig.colorbar(im, ax=ax, label="Messages")
    fig.tight_layout()
    return _fig_to_buffer(fig)


def _fig_to_buffer(fig: Figure) -> io.BytesIO:
    """Save figure to a BytesIO buffer and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf
