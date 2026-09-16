from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    subsystem: str
    severity: str
    message: str
    request_id: str


class LogService:
    def __init__(self) -> None:
        self.entries: list[LogEntry] = []

    def add(self, subsystem: str, severity: str, message: str) -> LogEntry:
        safe = message.replace("api_key", "[REDACTED]").replace("Authorization", "[REDACTED]")
        entry = LogEntry(
            datetime.now(UTC).strftime("%H:%M:%S"),
            subsystem,
            severity,
            safe[:300],
            str(uuid4())[:8],
        )
        self.entries.append(entry)
        return entry

    def filter(self, subsystem: str | None = None) -> list[LogEntry]:
        if subsystem in {None, "all"}:
            return self.entries[-100:]
        if subsystem == "errors":
            return [entry for entry in self.entries if entry.severity == "ERROR"][-100:]
        return [entry for entry in self.entries if entry.subsystem == subsystem][-100:]
