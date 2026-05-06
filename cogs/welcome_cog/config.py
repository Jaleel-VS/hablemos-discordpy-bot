"""Welcome cog configuration."""
from __future__ import annotations

from typing import Final

from config import get_int_env, get_list_env

COMMUNITY_CHANNEL_IDS: Final[list[int]] = [
    int(channel_id)
    for channel_id in get_list_env(
        "WELCOME_COMMUNITY_CHANNEL_IDS",
        [
            "243859172268048385",
            "399713966781235200",
            "296491080881537024",
        ],
    )
]

WELCOME_CHANNEL_ID: Final[int] = get_int_env(
    "WELCOME_CHANNEL_ID",
    "243838819743432704",
)

RAI_BOT_ID: Final[int] = get_int_env(
    "WELCOME_RAI_BOT_ID",
    "270366726737231884",
)

BEGINNER_ENGLISH_CHANNEL_ID: Final[int] = get_int_env(
    "WELCOME_BEGINNER_ENGLISH_CHANNEL_ID",
    "1005632020313014293",
)

BEGINNER_SPANISH_CHANNEL_ID: Final[int] = get_int_env(
    "WELCOME_BEGINNER_SPANISH_CHANNEL_ID",
    "1005631944689721354",
)

STAFF_ROLE_IDS: Final[set[int]] = {
    int(role_id)
    for role_id in get_list_env(
        "WELCOME_STAFF_ROLE_IDS",
        [
            "243854949522472971",
            "258819531193974784",
            "591745589054668817",
            "1014256322436415580",
            "1082402633979011082",
        ],
    )
}


# Modify this to add specific people to trigger the command
STAFF_USER_IDS: Final[set[int]] = {
    int(user_id)
    for user_id in get_list_env(
        "WELCOME_STAFF_USER_IDS",
        [
            "1078714238417248276",
        ],
    )
}

CUSTOMIZE_MENTION: Final[str] = "<id:customize>"

WELCOME_COLOR: Final[int] = 0x3498DB
