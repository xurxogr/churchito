"""Every Jinja template must at least compile.

Router tests mock the template engine, so a stray tag only shows up when a
real page is rendered in production. Compiling each file here catches that
before deploy.
"""

import pytest
from jinja2 import Environment, FileSystemLoader

from discord_bot.web.app import WEB_DIR

TEMPLATES_DIR = WEB_DIR / "templates"
TEMPLATE_NAMES = sorted(
    str(path.relative_to(TEMPLATES_DIR)) for path in TEMPLATES_DIR.rglob("*.html")
)


@pytest.mark.parametrize("name", TEMPLATE_NAMES)
def test_template_compiles(name: str) -> None:
    """Parsing the template raises on unbalanced or unknown tags.

    Args:
        name (str): Template path relative to the templates directory.
    """
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

    env.get_template(name)


def test_all_templates_are_covered() -> None:
    """Guard against the glob silently finding nothing."""
    assert "partials/cog_settings.html" in TEMPLATE_NAMES
