import json

from almond_ai.rag.service import RAGService


def test_rag_session_remove_and_reindex_restore_document(tmp_path):
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "policy.txt").write_text("approved onboarding policy", encoding="utf-8")
    users = tmp_path / "users.json"
    users.write_text(
        json.dumps({"users": [{"user_id": "local", "permissions": ["documents:read"]}]}),
        encoding="utf-8",
    )
    service = RAGService(documents, users, "keyword-local")

    assert service.status().documents == 1
    assert service.remove("policy.txt") == 1
    assert service.status().documents == 0
    assert service.search("onboarding", "local").matches == []

    restored = service.reindex()
    assert restored.documents == 1
    assert restored.last_index != "not recorded"


def test_rag_add_indexes_existing_approved_file(tmp_path):
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "policy.md").write_text("approved guidance", encoding="utf-8")
    users = tmp_path / "users.json"
    users.write_text('{"users": []}', encoding="utf-8")
    service = RAGService(documents, users, "keyword-local")

    record = service.add("policy.md")
    assert record.filename == "policy.md"
    assert len(record.chunks) == 1
