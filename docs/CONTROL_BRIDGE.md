# Developer control bridge (`almond ctl`)

A developer-only, local-only bridge that lets an agent (or a script)
drive a running Almond instance the same way a person at the keyboard
would: send it slash commands and chat messages, and read back its
status, logs, and a plain-text snapshot of the console.

It is **not** remote administration. It only ever binds to
`127.0.0.1`, it is disabled unless you explicitly turn it on, and it
never adds a shell/exec/eval/SQL path -- see
`src/almond_ai/control/protocol.py` for the exact set of actions it
will ever run.

## Enabling it

Disabled by default. Enable for one session only:

```powershell
$env:ALMOND_DEV_CONTROL_ENABLED = "true"
almond
```

With it unset (or `false`), every `almond ctl ...` command prints
`Developer control interface is disabled.` and exits without
connecting to anything.

## Live vs. automation sessions

- `--session automation` (the default) is isolated: its chat history
  and any pending write-confirmation never touch the visible console,
  the active view, or the real chat's conversation context.
- `--session live` drives the actual composer and console, so it
  appears exactly as if someone had typed it -- including switching
  the visible view, and including RAG/tool/deploy write confirmations,
  which still require the literal `CONFIRM`/`DEPLOY`/`ROLLBACK` text as
  a follow-up call. The bridge never supplies that text itself.

## The development loop

1. Edit Almond.
2. Launch it with the bridge enabled: `$env:ALMOND_DEV_CONTROL_ENABLED = "true"; almond`
3. In a second terminal: `almond ctl wait-ready --timeout 120`
4. Inspect: `almond ctl snapshot`
5. Exercise the feature: `almond ctl command "/pdf help"`
6. Inspect again: `almond ctl snapshot`
7. Check for errors: `almond ctl logs --last 20`
8. Fix code, restart Almond, repeat.

## Command reference

| Command | Purpose |
| --- | --- |
| `almond ctl ping` | Is a control-enabled instance reachable. |
| `almond ctl status [--json]` | Approved structured status fields. |
| `almond ctl state [--json]` | Fuller structured introspection (agents, tools, RAG, evaluations). |
| `almond ctl wait-ready [--timeout N]` | Poll until ready; exit 0 ready, 1 timeout, 2 connection/config, 3 auth. |
| `almond ctl chat "text" [--session live\|automation]` | Send a chat message. |
| `almond ctl command "/..." [--session live\|automation]` | Send a slash command. |
| `almond ctl logs [--last N] [--subsystem X] [--severity X] [--json]` | Recent, already-redacted log entries. |
| `almond ctl snapshot [--json]` | Plain-text semantic snapshot of the TUI (view, header, status, console, input). |

## Permissions and confirmation

The bridge calls the exact same registries, permission checks, and
audit logging the visible TUI uses (`ToolRegistry.authorize_run`,
`app.security.permissions`, the PDF/RAG write paths). A command that
would normally require typing `CONFIRM`/`DEPLOY`/`ROLLBACK` returns
`{"status": "confirmation_required", "required_text": "..."}` instead
of running -- the bridge never supplies that text on your behalf. See
`ApplicationDispatcher._resolve_pending` in
`src/almond_ai/control/dispatcher.py`.

## Known limitations

- Transport is a loopback TCP socket rather than a Windows named pipe
  (see the module docstring in `server.py` for why).
- `--session live` shares the one visible composer widget with a human
  operator; driving it while someone is mid-typing can overwrite their
  unsent text. Use `--session automation` for hands-off testing.
- `/exit` is refused outside `--session live`, so an automation call
  can never terminate the running instance.
- Token-file permissions are tightened with `chmod 0600` on a
  best-effort basis; this has limited effect on Windows ACLs, and the
  real guarantee is the loopback bind plus the random per-instance
  token, not the file mode.
