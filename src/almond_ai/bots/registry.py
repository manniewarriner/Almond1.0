"""Built-in bot definitions."""

from __future__ import annotations

from almond_ai.agents.registry import BASE_SYSTEM_PREAMBLE
from almond_ai.bots.models import BotDefinition

# id used for the "General Chat" nav item -- not part of "My Bots", but
# still an ordinary BotDefinition/AgentSession under the hood so it goes
# through the exact same session machinery as every other bot. General
# Chat is not a specialist: no unique_tool, no capability badge.
GENERAL_BOT_ID = "general"

# Bots shown in the staff-facing desktop app, in display order. Coding is
# deliberately excluded -- it stays terminal/developer-only. General Chat
# is added separately by callers (it isn't a specialist bot).
STAFF_BOT_IDS: tuple[str, ...] = ("calculator", "drafting", "document")

GENERAL_BOT = BotDefinition(
    id=GENERAL_BOT_ID,
    name="General Chat",
    description="Your local financial assistant",
    instructions="",  # empty -> falls back to the legacy AgentRegistry persona (bot_system_prompt)
    tools=["document_search", "document_to_pdf", "calculator"],
    rag_enabled=False,
    icon="▣",
    accent="#F15A24",
    built_in=True,
)

# Each specialist bot is built around exactly one signature capability
# (`unique_tool`) -- see almond_ai.tools.registry for what each tool
# actually does, and AlmondDeveloperApp._execute_tool for the WIP/
# experimental ones' canned, honest responses.
BUILT_IN_BOTS: tuple[BotDefinition, ...] = (
    BotDefinition(
        id="calculator",
        name="Calculator",
        description="UK pension tax calculators",
        instructions=(
            "Run deterministic UK pension calculations only: withdrawal tax, carry forward, "
            "and annual allowance. Never estimate these figures yourself -- the calculator "
            "tools already compute them precisely. Ask for whatever numbers are missing "
            "before calculating, and never present a result as personal financial advice."
        ),
        tools=["pension_withdrawal_tax", "carry_forward", "annual_allowance"],
        unique_tool="pension_withdrawal_tax",
        status="available",
        rag_enabled=False,
        icon="∑",
        accent="#8B5CF6",
        built_in=True,
    ),
    BotDefinition(
        id="drafting",
        name="Drafting",
        description="Draft professional client emails",
        instructions=(
            "Draft polished, professional UK financial-services client emails: a subject "
            "line, a concise and polite body, and (only if needed) a short 'Notes' section. "
            "Never invent client details, figures, facts, or status/outcome claims (e.g. that "
            "something was 'received', 'processed', or 'completed') you weren't explicitly "
            "given -- write '[assumed: ...]' inline for anything you had to assume, and ask "
            "for anything essential that's missing instead of guessing. Only state something "
            "as done or confirmed if the purpose/key points say so outright. You draft text "
            "only -- you never send, schedule, or deliver anything; that is not implemented."
        ),
        tools=["draft_client_email"],
        unique_tool="draft_client_email",
        status="available",
        rag_enabled=False,
        icon="✎",
        accent="#6E9BC7",
        built_in=True,
    ),
    BotDefinition(
        id="document",
        name="Document",
        description="Create branded Almond PDFs",
        instructions=(
            "Help turn a real local file into a branded PDF. Steer any file request toward "
            "'/pdf create <path> --title \"Title\"', which works on any real path on this "
            "machine. Never invent document content that wasn't in the source file."
        ),
        tools=["document_search", "document_to_pdf"],
        unique_tool="document_to_pdf",
        status="available",
        rag_enabled=True,
        icon="▣",
        accent="#F15A24",
        built_in=True,
    ),
    BotDefinition(
        id="coding",
        name="Coding",
        description="Local development agent",
        instructions=(
            "Local self-improvement/development is experimental and not implemented -- if "
            "asked to change Almond's own code, say so plainly. Never claim to modify files, "
            "run shell commands, execute SQL, merge changes, or touch production; none of "
            "that exists yet, and it will always require human review when it does."
        ),
        tools=["local_development"],
        unique_tool="local_development",
        status="experimental",
        rag_enabled=False,
        icon="△",
        accent="#D8637A",
        built_in=True,
    ),
)


def bot_system_prompt(bot: BotDefinition, fallback: str) -> str:
    """Build the system prompt for a bot's chat requests.

    `fallback` is the legacy `AgentRegistry.system_prompt()` output --
    used verbatim for the General Chat bot (empty `instructions`) so its
    behaviour, including `/agent use <name>` switching the active
    persona, is completely unchanged by the bot layer.
    """
    if not bot.instructions:
        return fallback
    return f"{BASE_SYSTEM_PREAMBLE} Active bot: {bot.name}. {bot.instructions}"
