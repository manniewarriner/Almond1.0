import pytest

from almond_ai.commands import command_suggestions, parse_command


def test_parse_quoted_rag_search():
    parsed = parse_command('/rag search "client onboarding"')
    assert parsed is not None
    assert parsed.name == "rag"
    assert parsed.args == ("search", "client onboarding")


def test_plain_text_is_not_command():
    assert parse_command("hello") is None


def test_invalid_quoting_is_safe_error():
    with pytest.raises(ValueError, match="Invalid quoting"):
        parse_command('/rag search "unfinished')


def test_command_completion_narrows():
    assert command_suggestions("/rag") == [
        "/rag status",
        "/rag search",
        "/rag inspect",
        "/rag reindex",
        "/rag add",
        "/rag remove",
    ]
