"""Shared Almond backend: one model provider, one session/bot layer, one
set of document/permission/audit services, used by both the Textual
terminal (almond_ai.app) and the desktop app (almond_ai.desktop).
"""

from __future__ import annotations

from almond_ai.core.application import AlmondCore, ModelProviderError

__all__ = ["AlmondCore", "ModelProviderError"]
