"""AlmondCode -- minimal, conversation-first coding CLI.

A separate entrypoint from the full developer-console TUI
(`almond_ai.app`). Prints a compact Almond Financial brand block once at
startup, then drops straight into a plain streaming chat REPL against
the "coding" bot -- no Textual, no sidebar, no panels. Shares the same
`AlmondCore` backend (provider, sessions, permissions) as every other
Almond UI, so it is one more thin front end, not a second model/session
stack.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from almond_ai.core.application import AlmondCore
from almond_ai.models.provider import ModelProviderError
from app.errors import ContentPolicyError
from app.safety.content_filter import enforce_safe_input

CODING_BOT_ID = "coding"

# Almond orange -- the same accent used for the brand icon/General bot
# elsewhere in the app (see almond_ai.bots.registry.GENERAL_BOT.accent).
_ACCENT = "\033[38;2;241;90;36m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

HELP_TEXT = "\n".join(
    [
        "/help    Show this message",
        "/clear   Clear conversation history",
        "/exit    Quit AlmondCode",
    ]
)

# Rotating diamond glyphs for the thinking indicator -- not a real spin,
# just enough glyph variety (filled/outline/pulse) to read as motion.
_SPINNER_FRAMES = ("◆", "◈", "◇", "◈")
_SPINNER_INTERVAL_SECONDS = 0.12


def _supports_color() -> bool:
    """Graceful ANSI fallback: honour NO_COLOR/FORCE_COLOR, else require a real TTY."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("FORCE_COLOR") is not None:
        return True
    return sys.stdout.isatty()


def _style(text: str, *codes: str) -> str:
    if not _supports_color():
        return text
    return f"{''.join(codes)}{text}{_RESET}"


def _model_label(model_filename: str) -> str:
    """"Qwen3.5-2B-Q4_K_M.gguf" -> "Qwen3.5-2B" -- drop the quantization suffix."""
    stem = Path(model_filename).stem
    parts = stem.split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else stem


def render_brand_block(core: AlmondCore, workspace: Path) -> str:
    """Compact startup identity block. Rendered once; never redrawn mid-session."""
    model_label = _model_label(core.config.model.model)
    status_word = "Local" if core.config.model.provider == "llama_cpp" else core.config.model.provider
    warming = "" if core.model_online() else _style(" (warming up)", _DIM)

    lines = [
        _style("◆ ", _ACCENT, _BOLD) + _style("Almond Financial", _BOLD),
        _style("AlmondCode", _ACCENT, _BOLD),
        "",
        _style("Local coding assistant", _DIM),
        f"{model_label} · {status_word} · Private{warming}",
        f"Workspace: {workspace}",
        "",
        _style("/help", _ACCENT) + " for commands",
    ]
    return "\n".join(lines)


async def _spin(stop: asyncio.Event) -> None:
    """Animated "◆ Thinking…" on the current line until `stop` is set, then clears it."""
    frame = 0
    line = ""
    while not stop.is_set():
        glyph = _SPINNER_FRAMES[frame % len(_SPINNER_FRAMES)]
        line = _style(glyph, _ACCENT, _BOLD) + _style(" Thinking…", _DIM)
        sys.stdout.write("\r" + line)
        sys.stdout.flush()
        frame += 1
        try:
            await asyncio.wait_for(stop.wait(), timeout=_SPINNER_INTERVAL_SECONDS)
        except TimeoutError:
            pass
    sys.stdout.write("\r" + " " * len(line) + "\r")
    sys.stdout.flush()


async def _stream_reply(core: AlmondCore) -> None:
    animate = sys.stdout.isatty()
    stop = asyncio.Event()
    spinner = asyncio.create_task(_spin(stop)) if animate else None

    async def _end_spinner() -> None:
        if spinner is not None and not stop.is_set():
            stop.set()
            await spinner

    try:
        first_chunk = True
        async for chunk in core.stream_reply(CODING_BOT_ID):
            if first_chunk:
                await _end_spinner()
                first_chunk = False
            sys.stdout.write(chunk)
            sys.stdout.flush()
    except ModelProviderError as exc:
        await _end_spinner()
        print(_style(f"[error] {exc}", _DIM))
        return
    finally:
        await _end_spinner()
    print()


async def _run() -> None:
    core = AlmondCore()
    workspace = Path.cwd()
    print(render_brand_block(core, workspace))
    print()
    try:
        while True:
            try:
                raw = input(_style("> ", _ACCENT, _BOLD))
            except (EOFError, KeyboardInterrupt):
                print()
                break
            text = raw.strip()
            if not text:
                continue
            if text in ("/exit", "/quit"):
                break
            if text == "/help":
                print(HELP_TEXT)
                continue
            if text == "/clear":
                core.sessions.get(CODING_BOT_ID).messages.clear()
                print(_style("Conversation cleared.", _DIM))
                continue
            try:
                safe_text = enforce_safe_input(text)
            except ContentPolicyError as exc:
                print(_style(str(exc), _DIM))
                continue
            core.append_user_message(CODING_BOT_ID, safe_text)
            await _stream_reply(core)
    finally:
        core.stop()


def run() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    run()
