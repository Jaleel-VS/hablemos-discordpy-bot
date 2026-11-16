"""Bare `$league` shows members the join reminder and the owner the admin usage."""
from __future__ import annotations

from dataclasses import dataclass, field

from cogs.league_cog.admin import LeagueAdminCog
from cogs.utils.guild import HOME_GUILD_ID

OWNER_ID = 1


@dataclass
class Author:
    id: int


@dataclass
class Guild:
    id: int = HOME_GUILD_ID


@dataclass
class Channel:
    id: int = 555


@dataclass
class Message:
    channel: Channel = field(default_factory=Channel)
    guild: Guild = field(default_factory=Guild)


@dataclass
class Context:
    author: Author
    guild: Guild = field(default_factory=Guild)
    message: Message = field(default_factory=Message)
    sent: list[str] = field(default_factory=list)
    replies: list[dict] = field(default_factory=list)

    async def send(self, content: str) -> None:
        self.sent.append(content)

    async def reply(self, **kwargs) -> None:
        self.replies.append(kwargs)


class FakeBot:
    async def is_owner(self, user: Author) -> bool:
        return user.id == OWNER_ID


async def test_members_get_the_reminder_once_per_channel_minute() -> None:
    cog = LeagueAdminCog(FakeBot())  # type: ignore[arg-type]
    first, second = Context(Author(2)), Context(Author(3))

    await cog.league_admin.callback(cog, first)  # type: ignore[arg-type]
    await cog.league_admin.callback(cog, second)  # type: ignore[arg-type]

    assert len(first.replies) == 1
    assert first.replies[0]["embed"].title == "🏆 Join the Language League!"
    assert first.replies[0]["mention_author"] is False
    assert second.replies == []


async def test_owner_gets_the_admin_usage() -> None:
    cog = LeagueAdminCog(FakeBot())  # type: ignore[arg-type]
    ctx = Context(Author(OWNER_ID))

    await cog.league_admin.callback(cog, ctx)  # type: ignore[arg-type]

    assert ctx.replies == []
    assert ctx.sent and ctx.sent[0].startswith("❌ Usage: `$league")
