from almond_ai.config import ModelSettings
from almond_ai.integrations.registry import integration_registry


def test_integration_status_reflects_local_filesystem(tmp_path):
    model = ModelSettings(provider="fake", model="synthetic")
    statuses = {item.name: item.status for item in integration_registry(tmp_path, model)}
    assert statuses["local filesystem"] == "online"
    assert statuses["RAG database"] == "online"
    assert statuses["model server"] == "development/mock"
    assert statuses["email"] == "not configured"


def test_integration_status_never_claims_unprobed_model_online(tmp_path):
    model = ModelSettings(provider="ollama")
    statuses = {item.name: item.status for item in integration_registry(tmp_path, model)}
    assert statuses["model server"] == "configured"


def test_missing_local_root_reports_unavailable(tmp_path):
    missing = tmp_path / "missing"
    statuses = {item.name: item.status for item in integration_registry(missing)}
    assert statuses["local filesystem"] == "unavailable"
    assert statuses["RAG database"] == "unavailable"
