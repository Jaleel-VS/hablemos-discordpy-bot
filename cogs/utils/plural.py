"""Pluralization helper for f-strings."""


class plural:
    """Format-spec pluralizer: f"{plural(5):reply}" → "5 replies"."""

    def __init__(self, value: int):
        self.value = value

    def __format__(self, format_spec: str) -> str:
        if self.value == 1:
            return f"{self.value} {format_spec}"
        # Handle irregular: "reply/replies"
        if "/" in format_spec:
            singular, pl = format_spec.split("/", 1)
            return f"{self.value} {pl}" if self.value != 1 else f"{self.value} {singular}"
        return f"{self.value} {format_spec}s"
