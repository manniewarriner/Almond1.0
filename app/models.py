"""Shared data models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class CheckStatus(StrEnum):
    OK = "ok"
    FAIL = "fail"


class HealthCheckItem(BaseModel):
    name: str
    status: CheckStatus
    detail: str


class HealthReport(BaseModel):
    items: list[HealthCheckItem]

    @property
    def ok(self) -> bool:
        return all(item.status == CheckStatus.OK for item in self.items)
