"""Launch the developer TUI while retaining legacy maintenance commands."""

from __future__ import annotations

import sys

LEGACY_COMMANDS = {"health", "calc", "search", "ask", "audit", "pdf"}


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "ctl":
        from almond_ai.control.cli import main as ctl_main

        ctl_main(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "desktop":
        from almond_ai.desktop.main import run as desktop_run

        desktop_run()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "code":
        from almond_ai.code_cli import run as code_run
        from almond_ai.platform import apply_windows_console_branding

        apply_windows_console_branding("code")
        code_run()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "dashboard":
        from almond_ai.app import run as dashboard_run
        from almond_ai.platform import apply_windows_console_branding

        apply_windows_console_branding("dashboard")
        dashboard_run()
        return
    if len(sys.argv) > 1 and sys.argv[1] in LEGACY_COMMANDS:
        from app.cli import main as legacy_main

        legacy_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] in {"--help", "-h"}:
        print(
            "AlmondCode\n\nUsage: almond [maintenance-command]\n"
            "Launch without arguments for AlmondCode, the minimal coding-assistant CLI.\n"
            "almond dashboard           Launch the full-screen developer console (sidebar/HUD, ctl bridge)\n"
            "almond desktop             Launch the staff-facing desktop app\n"
            "Maintenance commands: health, calc, search, ask, audit, pdf\n"
            "Developer control bridge (disabled by default, dashboard only): almond ctl --help"
        )
        return
    from almond_ai.code_cli import run as code_run
    from almond_ai.platform import apply_windows_console_branding

    apply_windows_console_branding("code")
    code_run()


if __name__ == "__main__":
    main()
