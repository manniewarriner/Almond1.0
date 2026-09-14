"""Provider-independent model interface.

Business logic must never depend on a single model provider. Callers only
ever interact with the Provider protocol, never a concrete provider class.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class ProviderMessage(BaseModel):
    role: str
    content: str


class ProviderResponse(BaseModel):
    text: str
    provider_name: str


class Provider(Protocol):
    name: str

    def complete(self, messages: list[ProviderMessage]) -> ProviderResponse: ...
