# Almond 1.0

Local-first desktop AI assistant for internal use at a small financial firm.
(This is a locally-renamed install of the `firm-ai` project -- the GitHub
repo and Google Drive copy still use the `firm-ai` name.)

Phases 0-8 are implemented: config/CLI skeleton, deterministic financial
calculator, document ingestion (Markdown/text/PDF), local keyword
retrieval with citations, a fake provider and full `ask` workflow, a real
HTTP provider adapter, a bundled local llama.cpp runtime and model,
fail-closed permission enforcement, and local audit logging. See
`AGENTS.md` for the full safety rules and phase plan, and
`docs/PILOT_RUNBOOK.md` for what a controlled internal pilot requires
before any wider rollout.

## AI Developer Console

Almond's primary interface is a real full-screen terminal (TUI) app for AI and
software development, launched via `almond` (no arguments). It reuses the
existing local configuration, retrieval, permissions, provider, and audit
seams. A separate `app.desktop` pywebview GUI previously existed alongside it
and has been removed; the terminal console is the supported interface.

The console provides:

- asynchronous chat through fake, Ollama, llama.cpp, or local OpenAI-compatible providers;
- multiline input, command history, slash autocomplete, cancellation, and clear actions;
- developer navigation for agents, tools, RAG, integrations, evaluations, logs,
  deployments, and safe configuration;
- READ/WRITE labels, fail-closed tool permissions, audit-ready metadata, redacted
  settings, and typed confirmations for destructive or deployment operations;
- a dark Almond Financial Textual theme with restrained orange focus and green status marks.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -e ".[dev]"
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
```

Textual installs through the project dependency set. Launch the developer console:

```bash
almond
```

On Windows, `Almond Developer Console.bat` provides a direct launcher. To create a
pinnable Start Menu entry with the Almond icon:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Install-DeveloperShortcut.ps1
```

Open Start, search for `Almond AI Developer Console`, then choose **Pin to taskbar**.
The launcher sets a stable Windows application identity and applies
`app/assets/almond.ico` to the console window. Windows Terminal may still group
terminal tabs under its own icon; the dedicated shortcut uses classic console hosting
to retain Almond branding.

### Local model configuration

Developer-console defaults use the bundled Qwen model through llama.cpp on loopback
(`127.0.0.1:11435`). The server starts on the first model request and stops when the
console closes. Override that default through environment values:

The Document bot's AI-formatting step runs a second, dedicated local model
(`ALMOND_DEV_MODEL__DOCUMENT_MODEL`, default `Qwen3.5-2B-Q4_K_M.gguf`) on its
own llama.cpp server (`127.0.0.1:11436`) rather than the chat model above --
it follows the strict block-classification JSON schema more reliably on
long documents. Only applies when `ALMOND_DEV_MODEL__PROVIDER=llama_cpp`.

```dotenv
ALMOND_DEV_MODEL__PROVIDER=ollama
ALMOND_DEV_MODEL__MODEL=llama3.1
ALMOND_DEV_MODEL__BASE_URL=http://localhost:11434
```

Supported provider values are `fake`, `ollama`, `llama_cpp`, and
`openai_compatible`. The final two use the standard local
`/v1/chat/completions` shape. Credentials can be supplied through
`ALMOND_DEV_MODEL__API_KEY` but are never rendered by `/config`.

### Developer commands

```text
/agent list                  /agent use compliance
/tools                       /tool inspect document_search
/rag status                  /rag search "client onboarding"
/integrations                /integration test model_server
/eval list                   /eval run retrieval-baseline
/logs model                  /logs errors
/deploy status               /deploy production
/config                      /clear
```

Use `Ctrl+Enter` to submit, `Ctrl+C` to cancel, `Ctrl+L` to clear the console,
`Ctrl+K` to clear input, `Tab` to autocomplete, arrow keys for history, `Esc` to
close suggestions, and `?` for shortcuts.

Production deployment requires typing `DEPLOY`; rollback and RAG write operations
also require typed confirmation. These adapters remain disabled/mock-only in this
developer build and cannot reach production.

### Implementation status

Fully functional: Textual shell, responsive navigation, bundled local model lifecycle,
fake/Ollama/OpenAI-compatible provider options, command parsing and autocomplete, agent
switching, `/ask`, `/summarise`, `/draft`, `/analyse`, deterministic calculations,
permission-checked tools, local keyword RAG search/add/remove/reindex, evaluation probes,
filtered developer logs, safe settings, error presentation, and legacy maintenance
command compatibility. RAG removal only changes the current session index; source files
remain untouched.

Intentionally unavailable pending owner-supplied endpoints, credentials, targets, and
approval: external email, CRM, compliance-data, staging/production deployment, and
rollback adapters. Confirmations remain fail-closed and never simulate successful
external actions.

Screenshot placeholder: `docs/screenshots/developer-console.png` (capture from an
approved development terminal; no client data should appear).

Edit `.env` if you need non-default values. Defaults work locally with the bundled model;
set `ALMOND_DEV_MODEL__PROVIDER=fake` for deterministic offline mock responses.

## Maintenance CLI

```bash
almond --help
almond health

almond calc percentage-return --start 100 --end 110
almond calc absolute-change --start 100 --end 90

almond search "KYC verification"
almond ask "What is required for client onboarding?"

almond audit --limit 20
```

`almond health` checks local readiness only: configuration loads and
validates, required local directories exist or can be created, local
audit storage (SQLite) can be initialized, provider configuration is
syntactically valid. No network call is made.

`almond search` / `almond ask` only read from `FIRM_AI_DOCUMENTS_DIR`
(default `data/sample_documents/`), enforce `documents:read` permission
via `data/users.json` (fail-closed: unlisted `--user` gets no access),
and always show citations or say plainly that no evidence was found.

`almond ask` uses the provider named by `FIRM_AI_PROVIDER_NAME`: `fake`
(default, deterministic, no network), `local` (Almond's bundled,
loopback-only `llama.cpp` server -- no internet, no API key, no
`FIRM_AI_PROVIDER_BASE_URL` required; see `app/providers/llama_cpp.py`),
or `approved` (a real HTTPS endpoint via `FIRM_AI_PROVIDER_BASE_URL` /
`FIRM_AI_PROVIDER_API_KEY` -- see `app/providers/http_provider.py`; not
exercised against a live endpoint anywhere in this repo).

`almond calc` performs deterministic financial arithmetic in application
code only -- never delegated to a model.

Every `search`, `ask`, and `calc` call is recorded locally via
`almond audit`. Exit codes across commands: `0` success, `1` a handled
error (bad input, permission denied, calculation error), `2` an
unexpected/configuration error.

Config env vars still use the `FIRM_AI_` prefix (unchanged, to match the
upstream repo and `.env.example`) even though the command is `almond`.

## Development

```bash
pytest
ruff check .
ruff format --check .
```

## Status

Phases 0-8 complete and tested. Not production-ready: see
`docs/PILOT_RUNBOOK.md` for exit criteria and `AGENTS.md` for the hard
safety rules that still apply. No trading, money movement, messaging,
record writes, deletion, shell/SQL execution, or production-system access
exist anywhere in this codebase.
