"""Higher-or-Lower cog configuration."""
from config import get_list_env

HOL_CHANNEL_IDS: list[int] = [int(x) for x in get_list_env("HOL_CHANNEL_IDS", ["247135634265735168"])]
