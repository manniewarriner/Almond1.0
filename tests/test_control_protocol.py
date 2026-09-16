from almond_ai.control import protocol


def test_forbidden_and_allowed_actions_never_overlap():
    assert protocol.ALLOWED_ACTIONS.isdisjoint(protocol.FORBIDDEN_ACTIONS)


def test_forbidden_actions_cover_the_agents_md_hard_prohibitions():
    assert protocol.FORBIDDEN_ACTIONS == {
        "shell",
        "exec",
        "python",
        "eval",
        "sql",
        "delete",
        "filesystem_write_raw",
        "process_launch",
    }


def test_allowed_actions_are_exactly_the_documented_set():
    assert protocol.ALLOWED_ACTIONS == {
        "ping",
        "status",
        "wait_ready",
        "chat",
        "command",
        "logs",
        "state",
        "snapshot",
    }


def test_request_limit_is_64kb():
    assert protocol.MAX_REQUEST_BYTES == 64 * 1024
