"""Typer CLI entry point."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.audit.log import AuditEvent, log_event, read_recent_events
from app.config import AppConfig, load_config
from app.documents.retrieval import format_citation, search_documents
from app.errors import (
    CalculationError,
    ConfigError,
    DocumentError,
    PdfGenerationError,
    PermissionDeniedError,
    ProviderError,
    RetrievalError,
)
from app.health import run_health_check
from app.models import CheckStatus
from app.pdf import create_branded_pdf
from app.providers.factory import get_provider
from app.security.permissions import resolve_requester
from app.tools.calculator import absolute_change, percentage_return, to_decimal
from app.workflows.ask import ask as run_ask_workflow

USER_OPTION = typer.Option(
    "local", "--user", envvar="FIRM_AI_USER_ID", help="Acting user id for permission checks"
)

app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Almond 1.0: local-first internal assistant"
)
calc_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Deterministic financial calculations."
)
pdf_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Branded Almond Financial PDF generation."
)
app.add_typer(calc_app, name="calc")
app.add_typer(pdf_app, name="pdf")
console = Console()


def _audit(
    config: AppConfig,
    user: str,
    command: str,
    request_summary: str,
    *,
    outcome: str,
    document_ids: list[str] | None = None,
    tools_invoked: list[str] | None = None,
    error_category: str | None = None,
) -> None:
    """Best-effort audit write: never lets a broken audit sink block the command."""
    event = AuditEvent(
        user_id=user,
        command=command,
        request_summary=request_summary,
        document_ids=document_ids or [],
        tools_invoked=tools_invoked or [],
        validation_result="ok" if error_category is None else "invalid",
        outcome=outcome,
        error_category=error_category,
    )
    try:
        log_event(config.audit_db_path, event)
    except (OSError, sqlite3.Error):
        console.print("[yellow]Warning: failed to write audit log entry.[/yellow]")


@app.callback()
def main_callback() -> None:
    """Almond 1.0: local-first internal assistant."""


@app.command()
def health(
    env_file: str = typer.Option(
        None, "--env-file", help="Path to an env file to load instead of .env"
    ),
) -> None:
    """Check local readiness: config, directories, audit storage, provider config syntax."""
    try:
        report = run_health_check(env_file)
    except Exception as exc:
        console.print(f"[red]Unexpected error during health check:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    table = Table(
        title="Almond 1.0 health check", title_style="bold #F2801E", header_style="#F2801E"
    )
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for item in report.items:
        color = "green" if item.status == CheckStatus.OK else "red"
        table.add_row(item.name, f"[{color}]{item.status.value}[/{color}]", item.detail)
    console.print(table)

    if not report.ok:
        raise typer.Exit(code=1)


@calc_app.command("percentage-return")
def calc_percentage_return(
    start: str = typer.Option(..., "--start", help="Starting value"),
    end: str = typer.Option(..., "--end", help="Ending value"),
    user: str = USER_OPTION,
) -> None:
    """Percentage return = (end - start) / start * 100."""
    try:
        config = load_config()
    except ConfigError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    summary = f"percentage-return start={start} end={end}"
    try:
        result = percentage_return(to_decimal(start), to_decimal(end))
    except CalculationError as exc:
        _audit(
            config, user, "calc.percentage-return", summary, outcome="error", error_category="calc"
        )
        console.print(f"[red]Calculation error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    _audit(config, user, "calc.percentage-return", summary, outcome="ok")
    console.print(f"{result}%")


@calc_app.command("absolute-change")
def calc_absolute_change(
    start: str = typer.Option(..., "--start", help="Starting value"),
    end: str = typer.Option(..., "--end", help="Ending value"),
    user: str = USER_OPTION,
) -> None:
    """Absolute change = end - start."""
    try:
        config = load_config()
    except ConfigError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    summary = f"absolute-change start={start} end={end}"
    try:
        result = absolute_change(to_decimal(start), to_decimal(end))
    except CalculationError as exc:
        _audit(
            config, user, "calc.absolute-change", summary, outcome="error", error_category="calc"
        )
        console.print(f"[red]Calculation error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    _audit(config, user, "calc.absolute-change", summary, outcome="ok")
    console.print(str(result))


@app.command()
def search(
    query: str = typer.Argument(..., help="Search terms"),
    top_k: int = typer.Option(5, "--top-k", help="Maximum results to return"),
    user: str = USER_OPTION,
) -> None:
    """Search approved local documents and show ranked, cited evidence.

    Access is enforced against data/users.json (fail-closed: an unknown
    --user gets zero permissions). Every call is recorded in the audit log.
    """
    try:
        config = load_config()
    except ConfigError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    requester = resolve_requester(config.users_file, user)

    try:
        result = search_documents(config.documents_dir, query, requester, top_k=top_k)
    except PermissionDeniedError as exc:
        _audit(config, user, "search", query, outcome="denied", error_category="permission_denied")
        console.print(f"[red]Search error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except RetrievalError as exc:
        _audit(config, user, "search", query, outcome="error", error_category="invalid_request")
        console.print(f"[red]Search error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    document_ids = [match.chunk.document_id for match in result.matches]
    _audit(config, user, "search", query, outcome="ok", document_ids=document_ids)

    if not result.has_evidence:
        console.print("[yellow]No evidence found for this query.[/yellow]")
        return

    table = Table(
        title=f"Search results for: {result.query}",
        title_style="bold #F2801E",
        header_style="#F2801E",
    )
    table.add_column("Score")
    table.add_column("Source")
    table.add_column("Excerpt")
    for match in result.matches:
        excerpt = match.chunk.text[:150].replace("\n", " ")
        table.add_row(f"{match.score:.2f}", format_citation(match.chunk), excerpt)
    console.print(table)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to ask"),
    top_k: int = typer.Option(5, "--top-k", help="Maximum evidence chunks to use"),
    user: str = USER_OPTION,
) -> None:
    """Ask a question. Answered only from approved local documents, with citations.

    Access is enforced against data/users.json (fail-closed: an unknown
    --user gets zero permissions). Every call is recorded in the audit log.
    """
    try:
        config = load_config()
    except ConfigError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    try:
        provider = get_provider(config)
    except ProviderError as exc:
        console.print(f"[red]Provider error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    requester = resolve_requester(config.users_file, user)
    local_server = getattr(provider, "server", None)

    try:
        try:
            result = run_ask_workflow(
                config.documents_dir, question, requester, provider, top_k=top_k
            )
        except PermissionDeniedError as exc:
            _audit(
                config, user, "ask", question, outcome="denied", error_category="permission_denied"
            )
            console.print(f"[red]Ask error:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        except RetrievalError as exc:
            _audit(config, user, "ask", question, outcome="error", error_category="invalid_request")
            console.print(f"[red]Ask error:[/red] {exc}")
            raise typer.Exit(code=1) from exc
    finally:
        # A one-shot CLI call must not leave the bundled model server running
        # in the background after the process exits.
        if local_server is not None:
            local_server.stop()

    citations = result.citations
    _audit(
        config,
        user,
        "ask",
        question,
        outcome="ok",
        document_ids=citations,
        tools_invoked=[f"provider:{provider.name}"],
    )

    console.print(result.answer)
    if result.has_evidence:
        console.print("\n[bold]Sources:[/bold]")
        for citation in citations:
            console.print(f"  - {citation}")
    else:
        console.print(
            "\n[yellow]No approved-document evidence was found for this question.[/yellow]"
        )


@pdf_app.command("create")
def pdf_create(
    source: str = typer.Argument(..., help="Path to the local document to convert"),
    title: str = typer.Option(None, "--title", help="Override the document title in the PDF"),
    user: str = USER_OPTION,
) -> None:
    """Convert a local document into an Almond Financial branded PDF.

    Access is enforced against data/users.json (fail-closed: an unknown
    --user gets zero permissions). Every call is recorded in the audit log.
    Supported source types: .txt .md .docx .pdf. Output is written under
    the configured outputs directory and never overwrites an existing file.
    """
    try:
        config = load_config()
    except ConfigError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    requester = resolve_requester(config.users_file, user)
    if "documents:read" not in requester.permissions:
        _audit(
            config,
            user,
            "pdf.create",
            f"source={Path(source).name}",
            outcome="denied",
            error_category="permission_denied",
        )
        console.print("[red]PDF error:[/red] Missing permission: documents:read")
        raise typer.Exit(code=1)

    try:
        result = create_branded_pdf(Path(source), config.outputs_dir, title)
    except (DocumentError, PdfGenerationError) as exc:
        _audit(
            config,
            user,
            "pdf.create",
            f"source={Path(source).name}",
            outcome="error",
            error_category="invalid_request",
        )
        console.print("[red]PDF generation failed.[/red]")
        console.print(f"\nReason:\n{exc}\n\nSupported:\n.txt .md .docx .pdf")
        raise typer.Exit(code=1) from exc

    _audit(
        config,
        user,
        "pdf.create",
        f"source={Path(source).name} pages={result.pages} output={Path(result.output_path).name}",
        outcome="ok",
        tools_invoked=["document_to_pdf"],
    )

    console.print("[bold]Almond PDF[/bold]\n")
    console.print("[green]✓[/green] Document loaded")
    console.print(f"[green]✓[/green] {result.word_count:,} words extracted")
    console.print("[green]✓[/green] Almond template applied")
    console.print("[green]✓[/green] PDF generated")
    console.print("[green]✓[/green] Output verified")
    console.print(f"\nOutput:\n{result.output_path}")


@app.command()
def audit(
    limit: int = typer.Option(20, "--limit", help="Maximum number of recent events to show"),
) -> None:
    """Show recent audit log events (local SQLite, read-only)."""
    try:
        config = load_config()
    except ConfigError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    events = read_recent_events(config.audit_db_path, limit=limit)

    if not events:
        console.print("[yellow]No audit events recorded yet.[/yellow]")
        return

    table = Table(title="Recent audit events", title_style="bold #F2801E", header_style="#F2801E")
    table.add_column("Time")
    table.add_column("User")
    table.add_column("Command")
    table.add_column("Outcome")
    table.add_column("Summary")
    for event in events:
        table.add_row(
            event["created_at"],
            event["user_id"],
            event["command"],
            event["outcome"],
            event["request_summary"],
        )
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
