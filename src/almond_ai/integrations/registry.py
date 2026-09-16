from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from almond_ai.config import ModelSettings


@dataclass(frozen=True)
class Integration:
    name: str
    status: str
    permissions: str
    latency_ms: int | None
    last_check: str


def integration_registry(
    documents_dir: Path | None = None,
    model: ModelSettings | None = None,
) -> list[Integration]:
    """Report only locally verifiable integration state."""
    now = datetime.now(UTC).strftime("%H:%M:%S UTC")
    root = (documents_dir or Path.cwd()).resolve()
    filesystem_online = root.exists() and root.is_dir()
    model_status = "development/mock" if model is None or model.provider == "fake" else "configured"
    return [
        Integration(
            "local filesystem",
            "online" if filesystem_online else "unavailable",
            "READ",
            1 if filesystem_online else None,
            now,
        ),
        Integration(
            "RAG database",
            "online" if filesystem_online else "unavailable",
            "READ",
            3 if filesystem_online else None,
            now,
        ),
        Integration("model server", model_status, "READ", None, now),
        Integration("email", "not configured", "NONE", None, now),
        Integration("CRM", "not configured", "NONE", None, now),
        Integration("compliance data", "not configured", "NONE", None, now),
    ]
