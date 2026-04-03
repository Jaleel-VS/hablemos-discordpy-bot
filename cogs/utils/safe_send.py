"""Safe message sending that handles the 2000-char Discord limit."""
import io

import discord


async def safe_send(
    dest: discord.abc.Messageable,
    content: str,
    *,
    filename: str = "response.txt",
    **kwargs,
) -> discord.Message:
    """Send *content*, falling back to a file attachment if it exceeds 2000 chars."""
    if len(content) <= 2000:
        return await dest.send(content, **kwargs)
    fp = io.BytesIO(content.encode("utf-8"))
    return await dest.send(file=discord.File(fp, filename=filename), **kwargs)
