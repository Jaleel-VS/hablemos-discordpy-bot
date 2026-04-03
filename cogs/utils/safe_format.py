"""Safe string formatter that never raises on missing or invalid keys."""
import string


class SafeFormatter(string.Formatter):
    """Format strings without crashing on missing keys or bad attribute access."""

    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            return kwargs.get(key, "")
        return super().get_value(key, args, kwargs)

    def get_field(self, field_name, args, kwargs):
        # Block private attribute access and deep nesting
        if field_name.count(".") > 2 or "._" in field_name:
            return ("", field_name)
        try:
            return super().get_field(field_name, args, kwargs)
        except (KeyError, AttributeError):
            return ("", field_name)


safe_format = SafeFormatter().format
