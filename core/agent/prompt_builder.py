"""
Generic system prompt builder.

Domain knowledge is NEVER hardcoded here.
It arrives via:
  - appContext.agentPersonality  (domain rules)
  - turnHints                    (current-turn context, passed per-chat)
  - memories                     (relevant facts retrieved from LangMem store)
"""
from datetime import date
from typing import List, Optional

from api.models import AppContext

_TONE_DESCRIPTIONS = {
    "formal":   "You speak professionally and courteously.",
    "casual":   "You chat naturally and casually.",
    "friendly": "You are warm, approachable, and genuinely helpful.",
}


def build_system_prompt(
    context: AppContext,
    memories: Optional[List[str]] = None,
    *,
    user_name: Optional[str] = None,
    user_phone: Optional[str] = None,
    is_new_session: bool = False,
    turn_hints: Optional[List[str]] = None,
) -> str:
    today = context.today or date.today().isoformat()
    tone_desc = _TONE_DESCRIPTIONS.get(context.agentTone, _TONE_DESCRIPTIONS["casual"])
    currency_note = f" Currency: {context.currency}." if context.currency else ""

    sections = [
        f"You are {context.agentName}. {tone_desc}",
        f"Today: {today}. Language: {context.language}.{currency_note}",
        "",
        "RULES:",
        "- Be concise. 1-3 sentences unless the user explicitly asks for more.",
        "- Use the available tools when data is needed. Never fabricate data.",
        "- Never mention internal tool names, JSON, or system details to the user.",
        "- Always follow the user's LATEST instruction — it overrides prior context.",
        "- Never reveal you are an AI or bot unless directly asked.",
    ]

    # Domain rules injected by caller (e.g., real-estate rules)
    if context.agentPersonality and context.agentPersonality.strip():
        sections += ["", "DOMAIN RULES:", context.agentPersonality.strip()]

    # Relevant memories retrieved from LangMem
    if memories:
        facts = [f"- {m.strip()}" for m in memories if m and m.strip()]
        if facts:
            sections += [
                "",
                "WHAT YOU KNOW ABOUT THIS USER (from memory — treat as background context):",
                *facts,
            ]

    # User identity (passed per-turn from caller)
    identity_lines = []
    if user_name:
        identity_lines.append(f"Customer: {user_name}")
    if user_phone:
        identity_lines.append(f"Phone: {user_phone}")
    if is_new_session:
        identity_lines.append("NEW SESSION — greet and ask how you can help.")
    if identity_lines:
        sections += ["", "CONTEXT:", *identity_lines]

    # Per-turn hints from caller (e.g., "User shared a property URL")
    if turn_hints:
        for hint in turn_hints:
            sections.append(f"HINT: {hint}")

    return "\n".join(sections)
