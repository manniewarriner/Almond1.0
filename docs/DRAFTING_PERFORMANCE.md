# Drafting performance profile

Only the Drafting bot uses this profile. General Chat retains its existing
system prompt, history selection, sampling settings, and request payload.
Desktop layout, styling, widgets, and design assets were not edited.

## Request changes

- A compact drafting-specific system prompt replaces the shared PDF/tool
  instructions. Output is the requested draft or structured text, with no
  preamble, commentary, or reasoning. Emails normally stay under 200 words.
- Guided New Draft and Edit Last Draft requests contain their complete fields,
  so they omit older conversations. Free-text revisions retain the current
  draft's original instructions and subsequent revisions, beginning at the
  latest guided draft. The visible transcript is retained.
- Request content has a conservative 3,000 UTF-8 byte budget, including the
  system prompt and relevant history. Oversized requests are explicitly rejected
  rather than silently dropping facts; use shorter key points or smaller sections.
- Draft output is capped at 512 tokens. If the server reports a length cutoff,
  the application reports an incomplete draft and does not save it as a completed
  assistant reply. It does not silently shorten the source to fit.
- Draft requests use temperature 0 and seed 42. This requests repeatable output;
  identical results across hardware/runtime versions are not guaranteed.
- llama.cpp requests enable prompt-cache reuse and retain
  `chat_template_kwargs: {enable_thinking: false}`. No-Think was already enabled
  before this work; the running MiniCPM5 template was checked to support it.
- Input cleanup normalizes line endings, excess spacing, BOM/zero-width artifacts,
  and soft-hyphen wrapping. It preserves figures, hard hyphens, paragraphs, and
  nested-list indentation. It does not guess at arbitrary broken words.
- The existing model, server and streaming worker are reused. No additional
  model is loaded and shared server/hardware settings are unchanged.

This does not replace the Document bot's deterministic PDF pipeline. Text supplied
to Drafting is already extracted; the model has no new file-access capability.

## Measurement

The running local server used `MiniCPM5-2B-Q4_K_M.gguf`. A synthetic request asked
for a short email proposing a review meeting, explicitly not confirming it.
On 2026-09-16 the new profile measured:

| Metric | Result |
| --- | ---: |
| First output text | 5.422 seconds |
| Complete draft | 10.867 seconds |
| Prompt tokens processed | 233 |
| Generated tokens | 64 |
| Draft words | 43 |

The draft ended normally, preserved the proposed/unconfirmed status, used a
placeholder sender, and contained no reasoning or explanation. The initial
legacy request had generated over 1,300 tokens without finishing when its
benchmark client was interrupted. That is not a completed baseline timing or
a claim about every request. Performance varies with prompt length, load,
cache state, and hardware; this is not an 8 GB memory-pressure benchmark.

Reproduce against an already-running loopback server with synthetic data:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_drafting.py --profile after
```

`--profile both` compares legacy/new prompts with a 512-token measurement cap
on both, unlike the uncapped legacy production request. The script reports
timings and the synthetic output; it neither starts nor stops the model server.

## Review and checks

61 focused drafting, shared-core, bot-session and desktop tests passed.
The review corrected nested-list indentation loss, preservation of earlier
revision constraints, and startup failures leaving the stream queue waiting.
Tests cover draft-only payload isolation, budget errors and rollback, original
facts in revisions, streaming output-limit reporting, and startup-error delivery.
Changed Python files pass Ruff lint and formatting checks.
