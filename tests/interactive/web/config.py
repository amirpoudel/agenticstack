"""
Default app configuration for the interactive test client.

Wires together prompts.py and tools.py into the payload sent to
POST /v1/apps/register on AgenticStack.

To test a different agent, change DEFAULT_APP_NAME to point at a different
entry in prompts.SYSTEM_PROMPTS and tools.*_TOOL_SCHEMAS, or add a new
config block and set DEFAULT_APP_CONFIG to it.
"""

from tests.interactive.web.prompts import SYSTEM_PROMPTS
from tests.interactive.web.tools import PROPERTY_TOOL_SCHEMAS

# ── Active test scenario ──────────────────────────────────────────────────────

DEFAULT_APP_NAME = "property_agent"

DEFAULT_APP_CONFIG: dict = {
    "appName": DEFAULT_APP_NAME,
    # Description is intentionally empty; runtime prompting is systemPrompt-only.
    "description": "",
    "systemPrompt": SYSTEM_PROMPTS[DEFAULT_APP_NAME],
    # Default state merged into every chat turn
    "state": {
        "domain": "real_estate",
        "currency": "NPR",
        "language": "en",
    },
    "tools": PROPERTY_TOOL_SCHEMAS,
    "structuredOutput": None,
}
