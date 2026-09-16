"""Shared application logic behind both the visible TUI and `almond ctl`.

`ApplicationDispatcher` wraps a running `AlmondDeveloperApp` instance and
exposes the operations the control bridge needs (chat, command, status,
state, logs, snapshot). It never re-implements command parsing,
permission checks, or write-confirmation rules -- every one of those
lives in `almond_ai.app` (the same registries, the same
`_command_output`, the same `parse_command`) and this module only adds
the bookkeeping needed to keep an automation session from touching the
visible console:

* LIVE_SESSION drives the real composer/console exactly as a human
  would (see `_run_live`): load the text into the composer, submit it,
  wait for any worker it starts, and read back what actually appeared.
* Any other session id gets its own isolated message history and its
  own pending-confirmation slot (`AlmondDeveloperApp._automation_pending`),
  so a scripted `/rag reindex` can never be confirmed by the operator
  typing CONFIRM in the real console, or vice versa.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual.widgets import Static, TextArea

from almond_ai.app import (
    CHAT_ROUTED_COMMAND_NAMES,
    CHAT_ROUTED_INSTRUCTIONS,
    FILE_CAPABILITY_ANSWER,
    LIVE_SESSION,
    is_file_capability_question,
)
from almond_ai.bots.registry import bot_system_prompt
from almond_ai.commands import parse_command
from almond_ai.control.protocol import PROTOCOL_VERSION
from almond_ai.models.provider import ModelProviderError
from app.errors import FirmAIError
from app.safety.content_filter import enforce_safe_input

if TYPE_CHECKING:
    from almond_ai.app import AlmondDeveloperApp

# How long an `almond ctl ... --session live` call waits for the worker
# it triggers (chat completion, an evaluation run, ...) before giving up
# and returning whatever has appeared in the console so far. A ctl call
# is a developer-loop tool, not the interactive TUI, so it needs a firm
# bound rather than waiting forever on a stalled provider.
LIVE_RESULT_TIMEOUT_SECONDS = 45.0


def _plain_text(value: Any) -> str:
    """Strip Rich markup from a string the app wrote with `escape()`/markup."""
    if isinstance(value, str):
        return Text.from_markup(value).plain
    return str(value)


def _clean(text: str | None) -> str | None:
    """Strip Rich markup from an automation-session result, if any.

    `_command_output` and its helpers were written for the RichLog
    console and freely embed markup like "[#F15A24]...[/]". The live
    session's console already renders that; an automation-session
    caller has no renderer at all, so it must see plain text.
    """
    return _plain_text(text) if isinstance(text, str) else text


class ApplicationDispatcher:
    def __init__(self, app: AlmondDeveloperApp) -> None:
        self.app = app
        self._session_messages: dict[str, list[dict[str, str]]] = defaultdict(list)

    # -- introspection -----------------------------------------------------

    async def ping(self) -> dict[str, Any]:
        return {"pong": True, "protocol_version": PROTOCOL_VERSION}

    def wait_ready_status(self) -> dict[str, Any]:
        app = self.app
        return {"ready": app.ready, "startup_state": "ready" if app.ready else "starting"}

    def get_status(self) -> dict[str, Any]:
        """Approved, structured fields only -- never a raw Python object."""
        app = self.app
        ready_check = getattr(app.provider, "is_ready", lambda: False)
        local_runtime_ready = bool(ready_check())
        if app.config.model.provider == "fake":
            provider_health = "mock"
        elif local_runtime_ready:
            provider_health = "online"
        else:
            provider_health = "ready"
        return {
            "application_running": True,
            "ready": app.ready,
            "startup_state": "ready" if app.ready else "starting",
            "active_view": app.active_view,
            "provider": app.config.model.provider,
            "model": app.config.model.model,
            "provider_health": provider_health,
            "local_runtime_ready": local_runtime_ready,
            "current_agent": app.agents.status().name,
            "rag_status": app.rag.status().indexing,
            "pdf_tool_available": app.tools.get("document_to_pdf").enabled,
            "control_protocol_version": PROTOCOL_VERSION,
        }

    def get_state(self) -> dict[str, Any]:
        """A fuller introspection view than `status`; still no raw objects."""
        app = self.app
        rag = app.rag.status()
        return {
            **self.get_status(),
            "agents": [agent.name for agent in app.agents.list()],
            "tools": [
                {
                    "name": tool.name,
                    "enabled": tool.enabled,
                    "read_only": tool.read_only,
                    "approval_required": tool.approval_required,
                    "last_status": tool.last_status,
                }
                for tool in app.tools.list()
            ],
            "rag": {
                "documents": rag.documents,
                "chunks": rag.chunks,
                "embedding_model": rag.embedding_model,
                "last_index": rag.last_index,
            },
            "evaluations": [
                {"name": suite.name, "status": suite.status} for suite in app.evals.list()
            ],
            "history_length": len(app.history),
            "live_confirmation_pending": app.pending_confirmation is not None,
        }

    def get_logs(
        self, limit: int = 20, subsystem: str | None = None, severity: str | None = None
    ) -> list[dict[str, str]]:
        if limit <= 0:
            return []
        entries = self.app.logs.filter(subsystem)
        if severity:
            entries = [entry for entry in entries if entry.severity.upper() == severity.upper()]
        entries = entries[-limit:]
        return [
            {
                "timestamp": entry.timestamp,
                "subsystem": entry.subsystem,
                "severity": entry.severity,
                "message": entry.message,
                "request_id": entry.request_id,
            }
            for entry in entries
        ]

    def get_snapshot(self) -> dict[str, Any]:
        """Semantic snapshot built from widget/app state, never a screen capture."""
        app = self.app
        header = [
            _plain_text(app.query_one("#welcome-heading", Static).content),
            _plain_text(app.query_one("#developer-heading", Static).content),
            _plain_text(app.query_one("#workflow-heading", Static).content),
        ]
        console = [_plain_text(entry) for entry in app.console_transcript[-40:]]
        input_text = app.query_one("#composer", TextArea).text
        return {
            "view": app.active_view,
            "header": header,
            "status": self.get_status(),
            "console": console,
            "input": input_text,
        }

    # -- chat / command ------------------------------------------------------

    async def chat(self, session: str, text: str) -> dict[str, Any]:
        if session == LIVE_SESSION:
            output = await self._run_live(text)
            return {"session": session, "text": output}
        resolved = self._resolve_pending(session, text)
        if resolved is not None:
            self.app._update_status()
            return {"session": session, "text": _clean(resolved)}
        if is_file_capability_question(text):
            return {"session": session, "text": _clean(FILE_CAPABILITY_ANSWER)}
        response = await self._generate_chat(session, text)
        return {"session": session, "text": _clean(response)}

    async def command(self, session: str, text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("command text must not be empty")
        if session == LIVE_SESSION:
            output = await self._run_live(text)
            pending = self.app.pending_confirmation
            if pending is not None:
                return {
                    "session": session,
                    "status": "confirmation_required",
                    "text": output,
                    "required_text": pending[1],
                }
            return {"session": session, "status": "ok", "text": output}

        app = self.app
        resolved = self._resolve_pending(session, text)
        if resolved is not None:
            app._update_status()
            return {"session": session, "status": "ok", "text": _clean(resolved)}

        parsed = parse_command(text)
        if parsed is None:
            raise ValueError("Command text must start with '/'")

        try:
            if parsed.name in CHAT_ROUTED_COMMAND_NAMES:
                output = await self._run_chat_routed_command(session, parsed.name, parsed.args)
            elif parsed.name == "eval" and parsed.args[:1] == ("run",):
                output = await self._run_eval_command(parsed.args)
            else:
                output = app._command_output(parsed.name, parsed.args, session=session)
        except (ValueError, PermissionError, FirmAIError) as exc:
            app.logs.add("tools", "ERROR", str(exc))
            raise
        finally:
            app._update_status()

        output = _clean(output)
        pending = app._automation_pending.get(session)
        if pending is not None:
            return {
                "session": session,
                "status": "confirmation_required",
                "text": output,
                "required_text": pending[1],
            }
        return {"session": session, "status": "ok", "text": output}

    # -- internals -----------------------------------------------------------

    def _resolve_pending(self, session: str, text: str) -> str | None:
        """Resolve an automation session's pending confirmation, if any.

        Mirrors `AlmondDeveloperApp.submit_input`'s confirmation branch,
        reusing the same `_perform_rag_action`/`_perform_tool_action`
        helpers, but never touches the live session's slot.
        """
        app = self.app
        pending = app._automation_pending.pop(session, None)
        if pending is None:
            return None
        action, required = pending
        if text != required:
            return "Confirmation rejected. Operation cancelled."
        try:
            if action.startswith("RAG "):
                return app._perform_rag_action(action)
            if action.startswith("TOOL "):
                return app._perform_tool_action(action)
        except (ValueError, PermissionError, FirmAIError) as exc:
            app.logs.add("rag", "ERROR", str(exc))
            raise
        app.logs.add("deploy", "WARNING", f"Confirmed mock action: {action}")
        return f"DEV / MOCK — {action} adapter unavailable."

    async def _run_chat_routed_command(self, session: str, name: str, args: tuple[str, ...]) -> str:
        if not args:
            raise ValueError(f"Usage: /{name} <text>")
        prompt = (
            " ".join(args)
            if name == "ask"
            else f"{CHAT_ROUTED_INSTRUCTIONS[name]}\n\n{' '.join(args)}"
        )
        return await self._generate_chat(session, prompt)

    async def _run_eval_command(self, args: tuple[str, ...]) -> str:
        app = self.app
        suite = args[1] if len(args) > 1 else "all"
        known = {item.name for item in app.evals.list()}
        if suite != "all" and suite not in known:
            raise ValueError(f"Unknown evaluation suite: {suite}")
        results = await app._run_probe_suite(suite)
        return "\n".join(
            f"{name}: {'PASS' if result.passed else 'FAIL'} "
            f"{result.latency_ms} ms — {result.detail}"
            for name, result in results
        )

    async def _generate_chat(self, session: str, prompt: str) -> str:
        app = self.app
        prompt = enforce_safe_input(prompt)
        messages = self._session_messages[session]
        before = len(messages)
        messages.append({"role": "user", "content": prompt})
        provider_messages = [
            {"role": "system", "content": self._system_prompt(session)},
            *messages[-20:],
        ]
        response = ""
        try:
            async for chunk in app.provider.stream(provider_messages):
                response += chunk
        except ModelProviderError as exc:
            del messages[before:]  # don't poison this session's history with the failed turn
            app.logs.add("model", "ERROR", str(exc))
            raise
        messages.append({"role": "assistant", "content": response})
        app.logs.add("model", "INFO", f"Automation chat completed (session={session})")
        return response

    def _system_prompt(self, session: str) -> str:
        """Use `session`'s persona when it names a known bot, e.g. `--session research`.

        Falls back to the legacy AgentRegistry persona for any other
        session name, so pre-existing automation sessions keep behaving
        exactly as before.
        """
        bot = self.app.sessions.bots.get(session)
        if bot is None:
            return self.app.agents.system_prompt()
        return bot_system_prompt(bot, self.app.agents.system_prompt())

    async def _run_live(self, text: str) -> str:
        """Drive the real composer/console exactly as a human operator would.

        Loads `text` into the visible composer and submits it through the
        unmodified `submit_input` -> `run_command`/`run_chat` path, then
        waits for whatever worker that starts, and returns the console
        lines that appeared as a result -- so a `--session live` call is
        indistinguishable, on the console, from a person typing it.
        """
        app = self.app
        before = len(app.console_transcript)
        composer = app.query_one("#composer", TextArea)
        composer.load_text(text)
        app.submit_input()
        try:
            await asyncio.wait_for(
                app.workers.wait_for_complete(), timeout=LIVE_RESULT_TIMEOUT_SECONDS
            )
        except TimeoutError:
            pass
        new_entries = app.console_transcript[before:]
        return "\n".join(_plain_text(entry) for entry in new_entries)
