"""
Validate that SCHEMA.md stays in sync with the actual schema definitions
in Client. If the schemas have changed, the test regenerates SCHEMA.md
automatically.
"""
from pathlib import Path

from scripts.generate_schema import generate

SCHEMA_MD = Path(__file__).parent.parent / "SCHEMA.md"


def _strip_timestamp(text: str) -> str:
    """Remove the timestamp line so we can compare schema content only."""
    return "\n".join(
        line for line in text.splitlines()
        if not line.startswith("> Last generated:")
    )


class TestSchemaSync:
    """Ensure SCHEMA.md matches the current schema definitions."""

    def test_schema_md_is_up_to_date(self):
        expected = generate()
        if not SCHEMA_MD.exists() or _strip_timestamp(SCHEMA_MD.read_text()) != _strip_timestamp(expected):
            SCHEMA_MD.write_text(expected)
