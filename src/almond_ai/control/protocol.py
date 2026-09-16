"""Wire protocol constants for the Almond developer control bridge.

Framing is newline-delimited JSON: exactly one JSON object per line,
terminated by ``\\n``. That keeps the transport to plain
``asyncio.start_server`` stream I/O (see server.py) with no extra
dependency and no ambiguity about message boundaries.
"""

from __future__ import annotations

PROTOCOL_VERSION = 1

# Hard cap on a single request line. Enforced both at the asyncio stream
# level (server.py passes this as the StreamReader `limit`) and again
# once the line is in hand, so an oversized request is always rejected
# cleanly rather than accepted piecemeal.
MAX_REQUEST_BYTES = 64 * 1024

# The complete set of actions the bridge will ever execute. Anything not
# in this set is rejected as `unknown_action` before any dispatch is
# attempted -- there is no default/fallback handler.
ALLOWED_ACTIONS = frozenset(
    {
        "ping",
        "status",
        "wait_ready",
        "chat",
        "command",
        "logs",
        "state",
        "snapshot",
    }
)

# Never dispatched under any circumstance, even if a future change to
# ALLOWED_ACTIONS were to collide with one of these names by mistake --
# checked first, and unconditionally, in server.py. This is the control
# bridge's half of the hard prohibitions in AGENTS.md (no shell, no
# arbitrary code execution, no SQL, no raw filesystem writes, no process
# launching): the TUI's command engine never exposed these to begin
# with, so this is a second, explicit lock on the same door.
FORBIDDEN_ACTIONS = frozenset(
    {
        "shell",
        "exec",
        "python",
        "eval",
        "sql",
        "delete",
        "filesystem_write_raw",
        "process_launch",
    }
)
