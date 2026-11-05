"""Discord message-link parsing shared by admin, summary and quote commands."""
import pytest

from cogs.utils.message_links import MessageLink, parse_message_link


@pytest.mark.parametrize("link", [
    "https://discord.com/channels/1/2/3",
    "https://canary.discord.com/channels/1/2/3",
    "https://ptb.discord.com/channels/1/2/3",
    "https://discordapp.com/channels/1/2/3",
    "http://discord.com/channels/1/2/3",
    " https://discord.com/channels/1/2/3/ ",
    "https://discord.com/channels/1/2/3?query=1",
])
def test_accepts_discord_message_links(link: str) -> None:
    assert parse_message_link(link) == MessageLink(1, 2, 3)


@pytest.mark.parametrize("link", [
    "",
    "not a link",
    "https://evil.com/channels/1/2/3",
    "https://discord.com/channels/1/2",
    "https://discord.com/channels/1/2/x",
    "https://discord.com/channels/@me/2/3",
])
def test_rejects_everything_else(link: str) -> None:
    assert parse_message_link(link) is None
