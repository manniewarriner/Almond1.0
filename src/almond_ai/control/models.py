"""Typed envelope models for the control protocol wire format.

Both ends agree on one shape via these models: the server builds every
response through `ControlResponse`, and the client parses every
response through it. Request/response *payloads* stay plain dicts
(action-specific, e.g. {"session": ..., "text": ...}), matching the
free-form `payload`/`result` shown in the protocol design.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from almond_ai.control.protocol import PROTOCOL_VERSION


class ControlRequest(BaseModel):
    version: int = PROTOCOL_VERSION
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    action: str
    token: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ControlError(BaseModel):
    code: str
    message: str


class ControlResponse(BaseModel):
    version: int = PROTOCOL_VERSION
    request_id: str | None = None
    ok: bool
    result: dict[str, Any] | None = None
    error: ControlError | None = None
