"""Small platform integrations for native Almond branding."""

from __future__ import annotations

import sys
from pathlib import Path

_icon_handle = None

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Each console-based front end gets its own taskbar identity/icon rather
# than inheriting the developer dashboard's -- AlmondCode is a distinct
# product from the Almond Financial dashboard, even though both are
# consoles sharing one AlmondCore backend.
_CONSOLE_APPS = {
    "dashboard": (
        "AlmondFinancial.AIDeveloperConsole",
        _PROJECT_ROOT / "app" / "assets" / "almond.ico",
    ),
    "code": (
        "AlmondFinancial.AlmondCode",
        _PROJECT_ROOT / "assets" / "almondcode.ico",
    ),
}


def apply_windows_console_branding(app: str = "dashboard") -> bool:
    """Set Almond identity and icon on a classic Windows console window.

    `app` selects which console front end is launching ("dashboard" or
    "code") so each gets its own AppUserModelID and taskbar icon.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        app_id, icon_path = _CONSOLE_APPS[app]
        shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        window = kernel32.GetConsoleWindow()
        if not window or not icon_path.is_file():
            return False
        image_icon = 1
        load_from_file = 0x10
        # Load the small (taskbar/titlebar) and big (Alt-Tab/jump list) slots
        # from their own correctly-sized frames in the .ico instead of
        # stretching one LR_DEFAULTSIZE-loaded bitmap for both -- that's what
        # made this icon look blurry even after the .ico itself gained
        # higher-resolution frames.
        small_handle = user32.LoadImageW(None, str(icon_path), image_icon, 16, 16, load_from_file)
        big_handle = user32.LoadImageW(None, str(icon_path), image_icon, 32, 32, load_from_file)
        if not small_handle or not big_handle:
            return False
        global _icon_handle
        _icon_handle = (small_handle, big_handle)
        user32.SendMessageW(window, 0x0080, 0, small_handle)
        user32.SendMessageW(window, 0x0080, 1, big_handle)
        return True
    except (AttributeError, OSError):
        return False
