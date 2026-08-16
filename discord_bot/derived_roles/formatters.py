"""Formatters for derived roles messages."""


def format_message(template: str | None = None, **kwargs: str | None) -> str:
    """Replace placeholders in a message.

    Unknown tokens and stray braces are left literal instead of raising.

    Args:
        template (str | None): Message template.
        **kwargs: Placeholders to replace.

    Returns:
        str: Formatted message.
    """
    result = template or ""
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", value or "")
    return result
