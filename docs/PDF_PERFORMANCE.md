# PDF conversion changes

PDF sources now use local PDFium text extraction (`pypdfium2==5.13.0`).
The existing pypdf extractor remains available through
`extract_document(..., pdf_backend="pypdf")` for comparison and diagnostics.
Output verification still uses pypdf. Desktop Create PDF now sends bounded text
snippets to the shared model server on this machine for structural formatting.
Remote model endpoints are rejected for this document-formatting step.

## AI-assisted desktop formatting

The desktop PDF worker now enables AI formatting by default. Extraction is
followed by MiniCPM5 structure classification, then branded rendering and
verification. It reuses the same provider/model instance as Drafting; no second
model is loaded. Each formatting batch has an independent document-only prompt,
so drafting conversations and previous documents are not added to it.

The model identifies short section headings and explicit bullet/numbered lists.
It returns only validated block IDs; rendered wording always comes from the
source. Ordinary prose and existing structured headings/tables are retained.
A short first line may be separated from a PDF paragraph for classification.
List previews are bounded, while the complete original list is retained in the
output. Nested lists and nonstandard numbering stay as original source text.
This is structural formatting, not AI rewriting, summarisation, or OCR.

Each batch contains at most 16 candidates and 1,900 bytes of candidate JSON.
The requests use temperature 0, seed 42, No-Think mode, prompt-cache reuse on
llama.cpp, JSON output, and a 512-token output limit. Progress reports the batch
being formatted. Model errors, malformed plans, or invented block IDs fail
before output creation instead of silently claiming AI formatting succeeded.
Audit records distinguish `ai_structure`, `mock_structure`, and `standard`.

AI inference adds work: large documents can take longer than the deterministic
pipeline. Existing page-range choices limit that work. The low-level PDF service
and terminal command retain deterministic defaults; the desktop worker opts in
through `AlmondCore.create_pdf(..., ai_format=True)`.

A live synthetic end-to-end check with the installed MiniCPM5 model completed
in 6.917 seconds, including AI formatting, a one-page render and verification.
The generated PDF preserved the test figures (1,234.56 and -12.5%) and the
qualification that the proposed meeting was not confirmed. Reproduce with:

```powershell
.\.venv\Scripts\python.exe scripts\verify_document_model.py
```

The script uses synthetic data in a temporary directory and starts/reuses the
local model server. It leaves that server available for the app.

## Desktop behaviour

- Streaming PDF uses `Page 1` numbering and avoids buffering/replaying page states.
  Standard layout retains `Page 1 of N`. Both use the same PDFium extraction.
- The default page scope is the entire document. First 25, first 50, and inclusive
  custom page ranges create excerpts. End pages beyond the document are clamped;
  invalid starts or reversed ranges fail before output creation.
- Excerpts identify the actual source range in the generated PDF, completion
  message, and audit record. Source files are never modified.
- Conversion results and errors survive navigation during the app session.
  The Document bot keeps its orange Create PDF button in the welcome panel;
  there is no duplicate Create PDF button beside the chat bar.
- Closing the main window during PDF creation or chat waits for the active
  workers to finish. The Qt event loop stays responsive; work is not terminated.
- Extraction cache payloads are immutable UTF-8 JSON, capped at 32 MiB and eight
  entries. Oversized entries are not cached. Path, size, modification timestamp,
  source range, and extraction backend identify each entry. Changed source
  versions are evicted; cache reads create independent content objects.

PDFium access is serialized because the native library is not thread-safe.
Document, page, and text-page handles are closed explicitly. Encrypted PDFs
(including those with empty passwords), unreadable PDFs, and PDFs without
extractable text are rejected. PDF text extraction does not perform OCR or
reproduce the original page layout.

## Reproducible measurements

The large-report measurements below concern extraction and deterministic
rendering only. They do not include the newly added AI formatting stage.

Run from the repository using its virtual environment:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_pdf_extraction.py data\sample_documents\etf-annual-report.pdf
.\.venv\Scripts\python.exe scripts\benchmark_pdf_conversion.py data\sample_documents\etf-annual-report.pdf
```

The extraction comparison disables the cache, outputs aggregate metrics only,
and does not print document text. The conversion benchmark writes its verified
PDF to a new temporary directory and prints the output path.

On 2026-09-16, the 1,174-page public sample produced these uncached extraction
results in one comparison run:

| Backend | Seconds | Characters |
| --- | ---: | ---: |
| PDFium | 11.752 | 4,982,616 |
| pypdf | 181.546 | 5,294,302 |

Aggregate word-token and numeric-token multiset overlap against pypdf was
99.95% for both. This is a coverage check, not proof of identical reading order,
layout, or semantic equivalence. Extraction times vary with machine load; an
earlier pypdf run took roughly 74 seconds. These extraction timings exclude
ReportLab rendering and output verification.

The subsequent full conversion completed in 219.05 seconds and verified 2,539
branded output pages containing 712,410 extracted words. Extraction and cache
preparation finished at 13.54 seconds; rendering finished at 217.57 seconds.
The template's pagination differs from the original report, so source and output
page counts are not expected to match. Rendering is now the dominant cost for
this unusually large sample.

Validation: 94 relevant extraction, PDF service, core, desktop, document, and CLI
tests passed. The modified Python files pass Ruff lint and formatting checks;
`pip check` reports no broken requirements.

The installed pypdfium2 wheel includes PDFium and its dependency license files;
retain these when distributing the desktop application.
