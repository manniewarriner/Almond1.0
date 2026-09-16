from __future__ import annotations

from rich.markup import escape

from app.documents.retrieval import RetrievalResult, format_citation


def render_rag_results(result: RetrievalResult) -> str:
    if not result.matches:
        return "No approved-document evidence found."
    rendered = []
    for index, match in enumerate(result.matches, start=1):
        chunk = match.chunk
        chunk_id = f"{chunk.document_id}:{chunk.page or index}"
        metadata = f"path={chunk.relative_path} title={chunk.title} page={chunk.page or '-'}"
        rendered.append(
            f"[b]{escape(format_citation(chunk))}[/b] score={match.score:.3f}\n"
            f"chunk={escape(chunk_id)} | {escape(metadata)}\n{escape(chunk.text[:240])}"
        )
    return "\n\n".join(rendered)
