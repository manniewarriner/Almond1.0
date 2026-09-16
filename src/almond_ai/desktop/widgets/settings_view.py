"""Minimal staff-facing Settings panel.

Deliberately small: no model/provider configuration, no permission
editing, no developer controls. Those remain terminal-only
(`/config`, `/permissions`, Deploy view).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from almond_ai import __version__
from almond_ai.core import AlmondCore


def _privacy_summary(core: AlmondCore) -> str:
    host = (core.config.model.base_url.host or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "Local model endpoint. No chat data leaves this machine."
    return "Remote model endpoint configured. Chat data may leave this machine."


class SettingsView(QWidget):
    def __init__(self, core: AlmondCore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(4)

        title = QLabel("Settings")
        title.setObjectName("botTitle")
        layout.addWidget(title)
        layout.addSpacing(18)

        self._model_value = self._section(layout, "Model status", "Checking…")
        self._section(layout, "Appearance", "Dark, fixed")
        self._privacy_value = self._section(layout, "Privacy", _privacy_summary(core))
        self._section(
            layout, "Default output location", str(Path(core.base_config.outputs_dir).resolve())
        )
        self._section(layout, "About Almond", f"Almond AI v{__version__}, staff desktop app")

        layout.addStretch(1)

    def _section(self, layout: QVBoxLayout, title: str, value: str) -> QLabel:
        layout.addSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("settingsSectionTitle")
        layout.addWidget(heading)
        value_label = QLabel(value)
        value_label.setObjectName("settingsValue")
        value_label.setWordWrap(True)
        layout.addWidget(value_label)
        return value_label

    def set_model_status(self, text: str) -> None:
        self._model_value.setText(text)
