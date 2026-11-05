"""Home server identity and language roles shared by every cog."""
from typing import Final

from config import get_int_env

HOME_GUILD_ID: Final[int] = get_int_env("HOME_GUILD_ID", 243838819743432704)
SPANISH_NATIVE_ROLE_ID: Final[int] = get_int_env("SPANISH_NATIVE_ROLE_ID", 243854128424550401)
ENGLISH_NATIVE_ROLE_ID: Final[int] = get_int_env("ENGLISH_NATIVE_ROLE_ID", 243853718758359040)
OTHER_NATIVE_ROLE_ID: Final[int] = get_int_env("OTHER_NATIVE_ROLE_ID", 247020385730691073)
LEARNING_SPANISH_ROLE_ID: Final[int] = get_int_env("LEARNING_SPANISH_ROLE_ID", 297415063302832128)
LEARNING_ENGLISH_ROLE_ID: Final[int] = get_int_env("LEARNING_ENGLISH_ROLE_ID", 247021017740869632)
