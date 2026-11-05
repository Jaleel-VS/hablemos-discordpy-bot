"""Collect user messages in a summary range."""


def collect_range_messages(
    history: list,
    start_msg,
    end_msg,
    *,
    include_link: bool = False,
    guild_id: int | None = None,
    channel_id: int | None = None,
) -> list[dict]:
    """Inclusive [start, end] user messages, keyed by id so boundaries
    are never appended twice (same-message range or API-inclusive history).
    """
    collected: dict[int, dict] = {}

    def _maybe_add(msg) -> None:
        if msg.author.bot or not msg.content.strip():
            return
        if msg.id in collected:
            return
        row = {
            "author": msg.author.display_name,
            "content": msg.content,
            "timestamp": msg.created_at,
        }
        if include_link and guild_id is not None and channel_id is not None:
            row["link"] = (
                f"https://discord.com/channels/{guild_id}/{channel_id}/{msg.id}"
            )
        collected[msg.id] = row

    for msg in history:
        _maybe_add(msg)
    _maybe_add(start_msg)
    _maybe_add(end_msg)
    return sorted(collected.values(), key=lambda m: m["timestamp"])
