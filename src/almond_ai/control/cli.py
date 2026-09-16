"""`almond ctl ...` -- developer-only local control bridge CLI.

Every command here first checks `ALMOND_DEV_CONTROL_ENABLED`; when it is
not set, the command prints exactly "Developer control interface is
disabled." and exits non-zero, without ever attempting to connect.
"""

from __future__ import annotations

import json as json_module

import typer

from almond_ai.config import load_developer_config
from almond_ai.control.client import (
    ControlAuthError,
    ControlClient,
    ControlUnavailableError,
    discover,
)
from almond_ai.control.models import ControlResponse
from app.config import load_config

ctl_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Developer-only local control bridge."
)

EXIT_TIMEOUT_OR_NOT_READY = 1
EXIT_CONNECTION_OR_CONFIG = 2
EXIT_AUTH_FAILURE = 3


def _require_enabled_client() -> ControlClient:
    dev_config = load_developer_config()
    if not dev_config.control_enabled:
        typer.echo("Developer control interface is disabled.")
        raise typer.Exit(code=EXIT_CONNECTION_OR_CONFIG)
    base_config = load_config()
    try:
        handle = discover(base_config.data_dir)
    except ControlUnavailableError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=EXIT_CONNECTION_OR_CONFIG) from exc
    return ControlClient(handle)


def _render(response: ControlResponse, as_json: bool) -> None:
    if as_json:
        typer.echo(json_module.dumps(response.result or {}, indent=2))
        return
    result = response.result or {}
    text = result.get("text")
    if isinstance(text, str):
        typer.echo(text)
        for key, value in result.items():
            if key != "text":
                typer.echo(f"({key}: {value})")
        return
    for key, value in result.items():
        typer.echo(f"{key}: {value}")


def _call(action: str, payload: dict | None, as_json: bool) -> None:
    client = _require_enabled_client()
    try:
        response = client.call(action, payload)
    except ControlAuthError as exc:
        typer.echo(f"Authentication failed: {exc}")
        raise typer.Exit(code=EXIT_AUTH_FAILURE) from exc
    except ControlUnavailableError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=EXIT_CONNECTION_OR_CONFIG) from exc
    if not response.ok:
        message = response.error.message if response.error else "unknown error"
        typer.echo(f"Error: {message}")
        raise typer.Exit(code=1)
    _render(response, as_json)


@ctl_app.command()
def ping(json_: bool = typer.Option(False, "--json")) -> None:
    """Check whether a control-enabled Almond instance is reachable."""
    _call("ping", None, json_)


@ctl_app.command()
def status(json_: bool = typer.Option(False, "--json")) -> None:
    """Show approved structured status fields."""
    _call("status", None, json_)


@ctl_app.command()
def state(json_: bool = typer.Option(False, "--json")) -> None:
    """Show a fuller structured introspection view than `status`."""
    _call("state", None, json_)


@ctl_app.command()
def snapshot(json_: bool = typer.Option(False, "--json")) -> None:
    """Show a plain-text semantic snapshot of the current TUI."""
    _call("snapshot", None, json_)


@ctl_app.command("wait-ready")
def wait_ready(timeout: float = typer.Option(120, "--timeout")) -> None:
    """Poll until Almond reports ready, or exit 1 on timeout."""
    dev_config = load_developer_config()
    if not dev_config.control_enabled:
        typer.echo("Developer control interface is disabled.")
        raise typer.Exit(code=EXIT_CONNECTION_OR_CONFIG)
    base_config = load_config()
    try:
        handle = discover(base_config.data_dir)
    except ControlUnavailableError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=EXIT_CONNECTION_OR_CONFIG) from exc
    client = ControlClient(handle)
    try:
        ready = client.wait_ready(timeout)
    except ControlAuthError as exc:
        typer.echo(f"Authentication failed: {exc}")
        raise typer.Exit(code=EXIT_AUTH_FAILURE) from exc
    if ready:
        typer.echo("ready")
        raise typer.Exit(code=0)
    typer.echo("Timed out waiting for Almond to become ready.")
    raise typer.Exit(code=EXIT_TIMEOUT_OR_NOT_READY)


@ctl_app.command()
def chat(
    text: str = typer.Argument(...),
    session: str = typer.Option("automation", "--session"),
    json_: bool = typer.Option(False, "--json"),
) -> None:
    """Send a chat message. Default session is isolated from the visible TUI."""
    _call("chat", {"session": session, "text": text}, json_)


@ctl_app.command()
def command(
    text: str = typer.Argument(...),
    session: str = typer.Option("automation", "--session"),
    json_: bool = typer.Option(False, "--json"),
) -> None:
    """Send a slash command. Default session is isolated from the visible TUI."""
    _call("command", {"session": session, "text": text}, json_)


@ctl_app.command()
def logs(
    last: int = typer.Option(20, "--last"),
    subsystem: str = typer.Option(None, "--subsystem"),
    severity: str = typer.Option(None, "--severity"),
    json_: bool = typer.Option(False, "--json"),
) -> None:
    """Show recent, already-redacted runtime log entries."""
    client = _require_enabled_client()
    payload = {"limit": last, "subsystem": subsystem, "severity": severity}
    try:
        response = client.call("logs", payload)
    except ControlAuthError as exc:
        typer.echo(f"Authentication failed: {exc}")
        raise typer.Exit(code=EXIT_AUTH_FAILURE) from exc
    except ControlUnavailableError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=EXIT_CONNECTION_OR_CONFIG) from exc
    if not response.ok:
        message = response.error.message if response.error else "unknown error"
        typer.echo(f"Error: {message}")
        raise typer.Exit(code=1)
    entries = (response.result or {}).get("entries", [])
    if json_:
        typer.echo(json_module.dumps(entries, indent=2))
        return
    if not entries:
        typer.echo("No runtime events recorded.")
        return
    for entry in entries:
        typer.echo(
            f"{entry['timestamp']} {entry['subsystem']:<12} "
            f"{entry['severity']:<7} {entry['message']}"
        )


def main(argv: list[str]) -> None:
    ctl_app(args=argv, prog_name="almond ctl")
