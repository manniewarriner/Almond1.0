"""Deterministic fake provider. No network calls, ever.

Used for local development and testing of the ask workflow. It does not
reason about anything; it builds a response only from the last user
message it is given, and it never executes instructions found in
document content passed to it as evidence.
"""

from __future__ import annotations

from app.providers.base import ProviderMessage, ProviderResponse


class FakeProvider:
    name = "fake"

    def complete(self, messages: list[ProviderMessage]) -> ProviderResponse:
        user_messages = [m.content for m in messages if m.role == "user"]
        last_user = user_messages[-1] if user_messages else ""
        text = f"[fake provider] Echo: {last_user}"
        return ProviderResponse(text=text, provider_name=self.name)
