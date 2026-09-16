"""Local-only developer control bridge for the Almond TUI.

Disabled by default (ALMOND_DEV_CONTROL_ENABLED=false). When enabled it
lets `almond ctl ...` connect to a running Almond instance, on
127.0.0.1 only, to check readiness, send chat/commands, and read back
status, logs, and a plain-text snapshot of the console -- all through
the same application logic the visible TUI uses, with the same
permissions and confirmation rules. It is not remote administration:
there is no shell, exec, or arbitrary code path anywhere in this
package (see almond_ai.control.protocol.FORBIDDEN_ACTIONS).
"""
