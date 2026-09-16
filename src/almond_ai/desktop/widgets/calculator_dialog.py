"""Guided input for the Calculator bot's three deterministic UK pension
calculations. Purely arithmetic -- every result comes from Decimal math in
app.tools.calculator, never from the local model. "Add File" is the one
model-assisted step: it only extracts raw figures already present in a
document to pre-fill these fields, verbatim, for the user to review before
calculating -- see almond_ai.core.calculator_extraction.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from almond_ai.core import AlmondCore
from almond_ai.desktop.workers import CalculatorScanWorker
from app.errors import CalculationError
from app.tools.calculator import (
    annual_allowance_position,
    carry_forward,
    pension_withdrawal_tax,
    to_decimal,
)

FILE_FILTER = (
    "Supported documents (*.txt *.md *.docx *.pdf *.png *.jpg *.jpeg *.bmp *.tiff);;All files (*.*)"
)

# calc type -> ordered (field key, label) pairs. Keys double as the model
# extraction schema's field names, so "Add File" can fill fields by key.
_CALC_FIELDS: dict[str, list[tuple[str, str]]] = {
    "Withdrawal tax": [
        ("withdrawal", "Withdrawal amount (£)"),
        ("other_taxable_income", "Other taxable income this year (£, optional)"),
    ],
    "Carry forward": [
        ("year_3_allowance", "3 years ago -- allowance (£)"),
        ("year_3_used", "3 years ago -- used (£)"),
        ("year_2_allowance", "2 years ago -- allowance (£)"),
        ("year_2_used", "2 years ago -- used (£)"),
        ("year_1_allowance", "Last year -- allowance (£)"),
        ("year_1_used", "Last year -- used (£)"),
    ],
    "Annual allowance": [
        ("net_income", "Net income (£)"),
        ("salary_sacrifice", "Salary sacrifice / flexible remuneration (£, optional)"),
        ("relief_at_source_contributions", "Relief at source contributions (£, optional)"),
        ("net_pay_contributions", "Net pay arrangement or other reliefs (£, optional)"),
        ("employer_contributions", "Employer contributions (£, optional)"),
        ("db_pension_input", "Defined benefit / cash balance pension input (£, optional)"),
        ("taxable_lump_sum_death_benefit", "Taxable lump sum death benefit (£, optional)"),
    ],
}


class CalculatorDialog(QDialog):
    def __init__(self, parent=None, core: AlmondCore | None = None) -> None:
        super().__init__(parent)
        self._core = core
        self._scan_worker: CalculatorScanWorker | None = None
        self.setWindowTitle("Calculator")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "Deterministic UK pension arithmetic -- never estimated by the local model. "
            "Illustrative only, not financial advice."
        )
        intro.setObjectName("dialogIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.type_combo = QComboBox()
        self.type_combo.addItems(list(_CALC_FIELDS))
        layout.addWidget(self.type_combo)

        self.pages = QStackedWidget()
        layout.addWidget(self.pages)
        self._fields: dict[str, dict[str, QLineEdit]] = {}
        for calc_type, field_specs in _CALC_FIELDS.items():
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            fields: dict[str, QLineEdit] = {}
            for key, label_text in field_specs:
                label = QLabel(label_text)
                label.setObjectName("fieldLabel")
                page_layout.addWidget(label)
                field = QLineEdit()
                page_layout.addWidget(field)
                fields[key] = field
            self._fields[calc_type] = fields
            self.pages.addWidget(page)
        self.type_combo.currentIndexChanged.connect(self.pages.setCurrentIndex)
        self.type_combo.currentIndexChanged.connect(lambda _: self.scan_status.setText(""))

        file_row = QHBoxLayout()
        self.add_file_button = QPushButton("Add File…")
        self.add_file_button.setObjectName("secondaryAction")
        self.add_file_button.setEnabled(self._core is not None)
        self.add_file_button.clicked.connect(self._on_add_file)
        file_row.addWidget(self.add_file_button)
        self.scan_status = QLabel("")
        self.scan_status.setObjectName("dialogIntro")
        self.scan_status.setWordWrap(True)
        file_row.addWidget(self.scan_status, 1)
        layout.addLayout(file_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Calculate")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._buttons = buttons

        self._result: tuple[str, str] | None = None

    # -- Add File (model-assisted extraction) -------------------------------

    def _on_add_file(self) -> None:
        if self._core is None or self._scan_worker is not None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a document to scan", str(Path.home()), FILE_FILTER
        )
        if not path:
            return
        calc_type = self.type_combo.currentText()
        field_keys = tuple(self._fields[calc_type])
        self._set_scanning(True)
        worker = CalculatorScanWorker(self._core, path, field_keys)
        worker.finished_ok.connect(lambda result, c=calc_type: self._on_scan_finished(c, result))
        worker.failed.connect(self._on_scan_failed)
        worker.finished.connect(self._on_scan_worker_done)
        self._scan_worker = worker
        worker.start()

    def _set_scanning(self, scanning: bool) -> None:
        self.add_file_button.setEnabled(not scanning and self._core is not None)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not scanning)
        self.type_combo.setEnabled(not scanning)
        if scanning:
            self.scan_status.setText("Scanning file…")

    def _on_scan_finished(self, calc_type: str, result: dict[str, str | None]) -> None:
        fields = self._fields[calc_type]
        found = 0
        for key, value in result.items():
            if value is None:
                continue
            field = fields.get(key)
            if field is None:
                continue
            field.setText(value)
            found += 1
        total = len(fields)
        plural = "s" if total != 1 else ""
        self.scan_status.setText(
            f"Found {found} of {total} field{plural} -- review before calculating."
        )

    def _on_scan_failed(self, message: str) -> None:
        self.scan_status.setText("")
        QMessageBox.warning(self, "File scan failed", message)

    def _on_scan_worker_done(self) -> None:
        self._scan_worker = None
        self._set_scanning(False)

    # -- Calculate ------------------------------------------------------------

    def _value(self, field: QLineEdit):
        text = field.text().strip()
        return to_decimal(text if text else "0")

    def _on_accept(self) -> None:
        calc_type = self.type_combo.currentText()
        fields = self._fields[calc_type]
        try:
            if calc_type == "Withdrawal tax":
                withdrawal = self._value(fields["withdrawal"])
                other_income = self._value(fields["other_taxable_income"])
                result = pension_withdrawal_tax(withdrawal, other_income)
                request = (
                    f"Withdrawal tax on £{withdrawal:,} withdrawal "
                    f"(other taxable income £{other_income:,})"
                )
                response = (
                    f"Tax-free lump sum: £{result['tax_free_amount']:,}\n"
                    f"Taxable amount: £{result['taxable_amount']:,}\n"
                    f"Tax due: £{result['tax_due']:,}\n"
                    f"Net amount: £{result['net_amount']:,}"
                )
            elif calc_type == "Carry forward":
                values = [self._value(field) for field in fields.values()]
                prior_years = tuple(zip(values[0::2], values[1::2], strict=True))
                result = carry_forward(prior_years)
                request = "Carry forward across the last 3 tax years"
                response = (
                    f"Unused carried forward: £{result['total_carry_forward']:,}\n"
                    f"Available this year: £{result['total_available_this_year']:,}"
                )
            else:
                values = [self._value(field) for field in fields.values()]
                result = annual_allowance_position(*values)
                tapered = " (tapered)" if result["tapered"] else ""
                request = f"Annual allowance position for net income £{values[0]:,}"
                response = (
                    f"Threshold income: £{result['threshold_income']:,}\n"
                    f"Adjusted income: £{result['adjusted_income']:,}\n"
                    f"Applicable annual allowance{tapered}: £{result['annual_allowance']:,}"
                )
        except CalculationError as exc:
            QMessageBox.warning(self, "Invalid input", str(exc))
            return
        self._result = (request, response)
        self.accept()

    @staticmethod
    def get_calculation(parent=None, core: AlmondCore | None = None) -> tuple[str, str] | None:
        dialog = CalculatorDialog(parent, core=core)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog._result
        return None
