"""Bounded, tool-free general-chat workflow for a local model."""

from __future__ import annotations

from pydantic import BaseModel

from app.providers.base import Provider, ProviderMessage
from app.safety.content_filter import enforce_safe_input, filter_safe_output

MAX_HISTORY_MESSAGES = 12
SYSTEM_PROMPT = (
    "You are Almond, a helpful general-purpose desktop assistant. Keep answers clear and "
    "accurate. Do not create sexually explicit or NSFW content. You have no tools and must "
    "never claim to have performed trades, money movement, messages, record changes, file "
    "changes, shell commands, SQL, or production-system actions."
)


class ChatResult(BaseModel):
    answer: str
    provider_name: str


def chat(
    message: str,
    history: list[ProviderMessage],
    provider: Provider,
) -> ChatResult:
    safe_message = enforce_safe_input(message)
    bounded_history = history[-MAX_HISTORY_MESSAGES:]
    messages = [
        ProviderMessage(role="system", content=SYSTEM_PROMPT),
        *bounded_history,
        ProviderMessage(role="user", content=safe_message),
    ]
    response = provider.complete(messages)
    return ChatResult(
        answer=filter_safe_output(response.text), provider_name=response.provider_name
    )
