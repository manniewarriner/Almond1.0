from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationSuite:
    name: str
    category: str
    status: str = "not run"


@dataclass(frozen=True)
class EvaluationResult:
    name: str
    passed: bool
    latency_ms: int
    detail: str


Probe = Callable[[], bool | tuple[bool, str] | Awaitable[bool | tuple[bool, str]]]


class EvaluationRunner:
    CATEGORIES = {
        "prompt-safety": "hallucination",
        "retrieval-baseline": "RAG",
        "tool-permissions": "tool use",
        "provider-latency": "latency",
    }

    def __init__(self) -> None:
        self._results: dict[str, EvaluationResult] = {}

    def list(self) -> list[EvaluationSuite]:
        return [
            EvaluationSuite(
                name,
                category,
                (
                    "pass"
                    if self._results.get(name, None) and self._results[name].passed
                    else ("fail" if name in self._results else "not run")
                ),
            )
            for name, category in self.CATEGORIES.items()
        ]

    async def run(self, name: str, probe: Probe) -> EvaluationResult:
        if name not in self.CATEGORIES:
            raise ValueError(f"Unknown evaluation suite: {name}")
        started = time.perf_counter()
        try:
            outcome = probe()
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if isinstance(outcome, tuple):
                passed, detail = outcome
            else:
                passed, detail = bool(outcome), "Probe completed"
        except Exception as exc:  # Evaluation failures become measured results.
            passed, detail = False, f"{type(exc).__name__}: {exc}"
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        result = EvaluationResult(name, passed, latency_ms, detail)
        self._results[name] = result
        return result

    def results(self) -> list[EvaluationResult]:
        return [self._results[name] for name in self.CATEGORIES if name in self._results]
