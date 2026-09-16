"""Desktop app entry point: `almond desktop`.

Boots the shared AlmondCore, shows a startup screen while any bundled
local model server warms up (never blocking the Qt event loop), then
opens MainWindow. Model warm-up runs on ModelStartupWorker (a QThread);
the GUI stays responsive and paints throughout.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QThread, QTimer
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from almond_ai.config import DeveloperConfig
from almond_ai.core import AlmondCore
from almond_ai.desktop import theme
from almond_ai.desktop.icons import nut_icon, nut_pixmap
from almond_ai.desktop.main_window import MainWindow
from almond_ai.desktop.workers import ModelStartupWorker

# Distinct from the terminal's app/assets/almond.ico (same orange badge,
# solid glyph instead of the terminal's outline mark) so the two apps are
# never confused in the taskbar or Alt-Tab. Falls back to the runtime nut
# icon if the .ico is ever missing (e.g. a stripped install).
_APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "almond-desktop.ico"

# Bundled so Roboto renders identically whether or not it's installed
# system-wide -- Windows ships no Roboto by default.
_FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_BUNDLED_FONTS = ("Roboto-Regular.ttf", "Roboto-Medium.ttf", "Roboto-Bold.ttf")


def _load_bundled_fonts() -> None:
    for filename in _BUNDLED_FONTS:
        path = _FONTS_DIR / filename
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))


def _app_icon() -> QIcon:
    if _APP_ICON_PATH.is_file():
        return QIcon(str(_APP_ICON_PATH))
    return nut_icon("almond", theme.ACCENT, size=64)


class _StartupScreen(QWidget):
    """The one deliberately animated moment in the whole app.

    A single breathing almond mark stands in for a generic progress bar --
    the loading indicator IS the brand, not decoration next to it.
    """

    # If model warm-up hasn't finished by this point, the titlebar close
    # button stops being ignored -- past here it's reasonable to conclude
    # something is stuck rather than genuinely still loading.
    _TIMEOUT_MS = 90_000

    def __init__(self, core: AlmondCore) -> None:
        super().__init__()
        self._core = core
        self._timed_out = False
        self.setWindowTitle("Almond AI")
        self.setWindowIcon(_app_icon())
        self.setFixedSize(380, 220)
        self.setStyleSheet(f"background: {theme.BG_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 36, 32, 36)
        layout.setSpacing(18)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        mark = QLabel()
        mark.setPixmap(nut_pixmap("almond", theme.ACCENT, size=48))
        mark.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(mark)

        self._opacity = QGraphicsOpacityEffect(mark)
        mark.setGraphicsEffect(self._opacity)
        self._pulse = QPropertyAnimation(self._opacity, b"opacity", self)
        self._pulse.setStartValue(1.0)
        self._pulse.setEndValue(0.35)
        self._pulse.setDuration(1100)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.finished.connect(self._reverse_pulse)
        self._pulse.start()

        title = QLabel("Starting Almond AI…")
        title.setObjectName("startupTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setWordWrap(True)
        title.setFixedWidth(300)
        layout.addWidget(title)
        self._title = title
        self._worker: QThread | None = None

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.setInterval(self._TIMEOUT_MS)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def set_worker(self, worker: QThread | None) -> None:
        self._worker = worker
        if worker is not None:
            self._timeout_timer.start()
        else:
            self._timeout_timer.stop()

    def _on_timeout(self) -> None:
        self._timed_out = True
        self.set_status(
            "Still starting — this is taking longer than expected.\nClose the window to cancel."
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        # Ignore a user-initiated close (titlebar X) while the model
        # warm-up thread -- and the llama-server.exe child process
        # ModelStartupWorker.run() may have already spawned via
        # local_server.start() -- is still running. This is the only
        # top-level widget at this point, so letting Qt's default
        # quitOnLastWindowClosed tear down the event loop here would exit
        # the process out from under that background thread/subprocess;
        # MainWindow's own finish-before-close guard never gets a chance
        # to run because MainWindow doesn't exist yet.
        #
        # Past _TIMEOUT_MS with no ready/failed signal, that protection
        # would otherwise trap the user with no way to exit but Task
        # Manager -- so stop the local server best-effort and let the
        # close proceed instead of ignoring it forever.
        if self._worker is not None and self._worker.isRunning():
            if self._timed_out:
                self._timeout_timer.stop()
                try:
                    self._core.stop()
                except Exception:  # noqa: BLE001 - best-effort on a forced exit
                    pass
                super().closeEvent(event)
                return
            event.ignore()
            return
        super().closeEvent(event)

    def _reverse_pulse(self) -> None:
        # QPropertyAnimation with loopCount doesn't auto-alternate direction,
        # so flip start/end each cycle for a smooth breathe-in/breathe-out
        # instead of a hard snap back to full opacity.
        start, end = self._pulse.endValue(), self._pulse.startValue()
        self._pulse.setStartValue(start)
        self._pulse.setEndValue(end)
        self._pulse.start()

    def set_status(self, text: str) -> None:
        self._title.setText(text)


def _apply_windows_app_id() -> None:
    """Distinct AppUserModelID from the terminal's so Windows taskbar/pinning
    treats the two apps separately instead of grouping them under one icon.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AlmondFinancial.Desktop")
    except (AttributeError, OSError):
        pass


def run(config: DeveloperConfig | None = None) -> None:
    _apply_windows_app_id()
    app = QApplication.instance() or QApplication(sys.argv)
    _load_bundled_fonts()
    app.setStyleSheet(theme.stylesheet())
    app.setWindowIcon(_app_icon())

    core = AlmondCore(config)

    splash = _StartupScreen(core)
    splash.show()

    state: dict[str, object] = {}

    def _open_main_window() -> None:
        window = MainWindow(core)
        window.setWindowIcon(_app_icon())
        window.show()
        state["window"] = window
        splash._pulse.stop()
        splash.set_worker(None)
        splash.close()

    local_server = getattr(core.provider, "local_server", None)
    if local_server is None:
        _open_main_window()
    else:
        splash.set_status("Loading the local model. This can take a minute.")
        worker = ModelStartupWorker(core)

        def _on_ready() -> None:
            splash.set_status("Model ready.")
            _open_main_window()

        def _on_failed(message: str) -> None:
            splash.set_status(f"Model unavailable: {message}")
            # Open anyway -- General Chat and the Document/Drafting bots
            # degrade to a clear "offline" status rather than a stuck
            # splash screen; the user can retry once the model is fixed.
            _open_main_window()

        worker.ready.connect(_on_ready)
        worker.failed.connect(_on_failed)
        state["worker"] = worker
        splash.set_worker(worker)
        worker.start()

    sys.exit(app.exec())
