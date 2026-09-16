from almond_ai.ui.widgets.rag_results import render_rag_results
from app.documents.models import DocumentChunk
from app.documents.retrieval import RetrievalResult, RetrievedChunk


def test_rag_result_renders_source_score_excerpt_metadata_and_chunk_id():
    chunk = DocumentChunk(
        document_id="doc-123",
        filename="synthetic-policy.md",
        relative_path="policies/synthetic-policy.md",
        title="Synthetic policy",
        page=2,
        text="Synthetic content only.",
    )
    result = RetrievalResult(query="policy", matches=[RetrievedChunk(chunk=chunk, score=0.75)])
    rendered = render_rag_results(result)
    assert "synthetic-policy.md" in rendered
    assert "score=0.750" in rendered
    assert "chunk=doc-123:2" in rendered
    assert "path=policies/synthetic-policy.md" in rendered
    assert "Synthetic content only." in rendered
