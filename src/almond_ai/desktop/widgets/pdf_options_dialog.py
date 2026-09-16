"""Small, local-only options dialog for branded PDF creation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class PdfOptions:
    fast: bool
    page_range: tuple[int, int] | None


class PdfOptionsDialog(QDialog):
    """Collect speed/layout and page-scope choices before conversion."""

    def __init__(self, source_path: str, parent=None) -> None:
        super().__init__(parent)
        self._is_pdf = Path(source_path).suffix.lower() == ".pdf"
        self.setWindowTitle("Create branded PDF")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        intro = QLabel(
            "Create an Almond-branded PDF from the document's text. "
            "Choose fewer pages for a quicker excerpt."
        )
        intro.setObjectName("dialogIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(10)

        self.mode = QComboBox()
        self.mode.setObjectName("pdfMode")
        self.mode.addItem("Streaming PDF", True)
        self.mode.addItem("Standard layout", False)
        form.addRow("Format", self.mode)

        self.scope = QComboBox()
        self.scope.setObjectName("pdfPageScope")
        self.scope.addItem("Entire document", "all")
        self.scope.addItem("First 25 pages", "first25")
        self.scope.addItem("First 50 pages", "first50")
        self.scope.addItem("Custom range", "custom")
        self.scope.setEnabled(self._is_pdf)
        form.addRow("Pages", self.scope)

        self.range_widget = QWidget()
        range_layout = QHBoxLayout(self.range_widget)
        range_layout.setContentsMargins(0, 0, 0, 0)
        self.start_page = QSpinBox()
        self.start_page.setRange(1, 99999)
        self.start_page.setValue(1)
        self.end_page = QSpinBox()
        self.end_page.setRange(1, 99999)
        self.end_page.setValue(25)
        range_layout.addWidget(self.start_page)
        range_layout.addWidget(QLabel("to"))
        range_layout.addWidget(self.end_page)
        self.range_label = QLabel("Range")
        form.addRow(self.range_label, self.range_widget)
        layout.addLayout(form)

        self.note = QLabel(
            "Page selection applies to PDF source files only. Standard layout includes "
            "'Page 1 of 10'; streaming PDF uses 'Page 1' and uses less memory."
        )
        self.note.setObjectName("dialogIntro")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create PDF")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.scope.currentIndexChanged.connect(self._update_range_visibility)
        self.start_page.valueChanged.connect(self._keep_range_valid)
        self._update_range_visibility()

    def _update_range_visibility(self) -> None:
        custom = self._is_pdf and self.scope.currentData() == "custom"
        self.range_widget.setVisible(custom)
        self.range_label.setVisible(custom)

    def _keep_range_valid(self, start: int) -> None:
        self.end_page.setMinimum(start)

    def _accept_if_valid(self) -> None:
        self._keep_range_valid(self.start_page.value())
        self.accept()

    def options(self) -> PdfOptions:
        scope = self.scope.currentData() if self._is_pdf else "all"
        ranges = {
            "first25": (1, 25),
            "first50": (1, 50),
            "custom": (self.start_page.value(), self.end_page.value()),
        }
        return PdfOptions(fast=bool(self.mode.currentData()), page_range=ranges.get(scope))

    @staticmethod
    def get_options(source_path: str, parent=None) -> PdfOptions | None:
        dialog = PdfOptionsDialog(source_path, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.options()
        return None
