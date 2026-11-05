"""Quote usernames follow the shared native-role color precedence."""
from types import SimpleNamespace

import pytest

from cogs.quote_generator_cog.config import (
    ROLE_COLOR_ENGLISH_NATIVE,
    ROLE_COLOR_OTHER_NATIVE,
    ROLE_COLOR_SPANISH_NATIVE,
)
from cogs.quote_generator_cog.main import username_color_for_member
from cogs.utils.guild import (
    ENGLISH_NATIVE_ROLE_ID,
    OTHER_NATIVE_ROLE_ID,
    SPANISH_NATIVE_ROLE_ID,
)


@pytest.mark.parametrize(("role_ids", "expected"), [
    ([ENGLISH_NATIVE_ROLE_ID, OTHER_NATIVE_ROLE_ID, SPANISH_NATIVE_ROLE_ID], ROLE_COLOR_SPANISH_NATIVE),
    ([OTHER_NATIVE_ROLE_ID], ROLE_COLOR_OTHER_NATIVE),
    ([ENGLISH_NATIVE_ROLE_ID], ROLE_COLOR_ENGLISH_NATIVE),
    ([999], None),
])
def test_username_color_for_member(role_ids: list[int], expected: tuple[int, int, int] | None) -> None:
    member = SimpleNamespace(roles=[SimpleNamespace(id=role_id) for role_id in role_ids])
    assert username_color_for_member(member) == expected
