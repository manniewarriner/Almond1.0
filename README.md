# Almond 1.0

Local-first desktop AI assistant for internal use at a small financial firm.
(This is a locally-renamed install of the `firm-ai` project -- the GitHub
repo and Google Drive copy still use the `firm-ai` name.)

Phases 0-8 are implemented: config/CLI skeleton, deterministic financial
calculator, document ingestion (Markdown/text/PDF), local keyword
retrieval with citations, a fake provider and full `ask` workflow, a real
HTTP provider adapter (mocked in tests, never called live in this repo),
fail-closed permission enforcement, and local audit logging. See
`AGENTS.md` for the full safety rules and phase plan, and
`docs/PILOT_RUNBOOK.md` for what a controlled internal pilot requires
before any wider rollout.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -e ".[dev]"
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
```

Edit `.env` if you need non-default values. Defaults work out of the box
with the `fake` provider (no API key required, no network call).

## Desktop app

Double-click `Almond.bat` or the Almond desktop shortcut. The native app opens
without a terminal and provides General Chat, Ask, Search, Calculator, Audit,
and Health tabs.
All existing permission, evidence, citation, and audit controls remain active.

General Chat starts Almond's bundled `llama.cpp` server invisibly on
`127.0.0.1:11435`, using `FIRM_AI_LOCAL_CHAT_MODEL` (default
`Qwen3.5-2B-Q4_K_M.gguf`). It has no cloud fallback, no tools, bounded
conversation history, and deterministic NSFW filtering. The local server stops
when Almond closes.
Document Ask remains a separate evidence-only workflow.

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
(default, deterministic, no network), `local`/`approved` (a real HTTPS
endpoint via `FIRM_AI_PROVIDER_BASE_URL` / `FIRM_AI_PROVIDER_API_KEY` --
see `app/providers/http_provider.py`; not exercised against a live
endpoint anywhere in this repo).

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
