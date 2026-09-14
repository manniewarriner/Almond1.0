# Phase 8 — Controlled Internal Pilot Runbook

This document is the Phase 8 deliverable. It cannot be executed by an AI
agent alone: a pilot requires real firm staff, a real (if small) group of
approved documents, and a human decision-maker to authorize it. What
follows is the checklist and guardrails for running it.

## Scope

- **In scope:** `firm-ai ask`, `firm-ai search`, `firm-ai calc`, run
  locally by a small group (2-5) of internal staff, against a small set
  of **already-public or explicitly-approved-for-pilot** internal
  documents. Synthetic or non-sensitive documents only until a separate,
  explicit sign-off covers real internal documents.
- **Out of scope (still true after Phase 8):** trading, money movement,
  email/messaging, client record writes, file/record deletion, shell or
  SQL execution, production system access, real client data. Nothing in
  this codebase implements any of these; the pilot does not change that.

## Pre-pilot checklist

- [ ] `firm-ai health` passes for every pilot participant's machine.
- [ ] `data/users.json` lists exactly the pilot participants, each with
      only `documents:read` (no other permission exists yet).
- [ ] `data/sample_documents/` contains only documents approved for this
      pilot by the document owner, not raw client or production data.
- [ ] `.env` uses `FIRM_AI_PROVIDER_NAME=fake` unless a specific approved
      endpoint has been separately reviewed and its credentials handled
      per the firm's secrets policy (never committed to any repo).
  - `.env.example` values are the current field expectations for
    `local` and `approved` providers, set in Phase 6.
- [ ] Every participant knows: this tool never takes an action on their
      behalf, only answers questions and searches documents.
- [ ] A named person owns audit review for the pilot window (see below).

## During the pilot

- Participants run `firm-ai ask "<question>"` and `firm-ai search "<query>"`
  against the approved document set only.
- Every call is recorded locally via `firm-ai audit` (see `app/audit/log.py`,
  wired into `search`, `ask`, and `calc` in Phase 8). The pilot owner should
  run `firm-ai audit --limit 100` periodically and look for:
  - unexpected `denied` outcomes (a participant hitting a permission
    they should or shouldn't have),
  - `error` outcomes (bad input, or a real bug),
  - any `request_summary` that looks like it's testing a boundary
    (attempted path traversal strings, injected instructions, etc. --
    these are expected as part of intentional red-teaming, see below).
- Encourage participants to **try to break it**: ask it to do something
  out of scope, paste document text containing fake instructions, ask
  about documents it shouldn't have access to. Log what happens. This is
  cheaper and safer to find during a pilot than after wider rollout.

## Stopping / rollback

- Pilot can be stopped by any participant or the pilot owner at any time
  with no cleanup required: it is a local CLI tool with no external state
  beyond the local `data/audit.db` and whatever `.env` points at.
- If an unexpected write-capable or irreversible action is ever observed,
  stop the pilot immediately and treat it as a severity-1 bug -- nothing
  in the current design should be capable of this (see `AGENTS.md` hard
  prohibitions), so its occurrence means a rule was violated somewhere
  and needs root-causing before continuing.

## Exit criteria (before considering anything beyond pilot)

- [ ] No permission bypass found (every `denied` in the audit log is one
      that should have been denied).
- [ ] No prompt-injection-driven behavior change observed (evidence text
      containing "instructions" never altered what the tool actually did).
- [ ] No unhandled exceptions / raw tracebacks shown to a participant.
- [ ] Feedback collected from every participant on answer usefulness and
      citation accuracy.
- [ ] A named decision-maker has explicitly signed off in writing before:
      real client data is used, a new tool (beyond search/calc) is added,
      or any write-capable action is proposed. None of that is implied by
      pilot completion.

## Explicitly not claimed

Completing this pilot does not constitute production readiness. Per the
project's own working rules, that additionally requires a security review,
a privacy review, an operational review, and a model-quality review, none
of which have been performed as part of Phases 0-8.
