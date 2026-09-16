from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_permission: str
    read_only: bool = True
    timeout_seconds: int = 30
    approval_required: bool = False
    audit_required: bool = True
    source: str = "builtin"
    enabled: bool = True
    last_status: str = "never"


class ToolRegistry:
    def __init__(self) -> None:
        empty = {"type": "object", "properties": {}}
        self._tools = {
            "document_search": ToolDefinition(
                "document_search", "Search approved local documents", empty, empty, "documents:read"
            ),
            "calculator": ToolDefinition(
                "calculator", "Deterministic financial calculations", empty, empty, "calculator:use"
            ),
            "rag_reindex": ToolDefinition(
                "rag_reindex",
                "Rebuild local knowledge index",
                empty,
                empty,
                "documents:write",
                read_only=False,
                approval_required=True,
            ),
            "document_to_pdf": ToolDefinition(
                "document_to_pdf",
                "Convert an approved local document into an Almond Financial branded PDF",
                {
                    "type": "object",
                    "properties": {
                        "source_path": {"type": "string"},
                        "title": {"type": "string"},
                    },
                    "required": ["source_path"],
                },
                {
                    "type": "object",
                    "properties": {
                        "output_path": {"type": "string"},
                        "pages": {"type": "integer"},
                    },
                },
                "documents:read",
                read_only=False,
            ),
            "deployment": ToolDefinition(
                "deployment",
                "Controlled deployment adapter",
                empty,
                empty,
                "deploy:write",
                read_only=False,
                approval_required=True,
                enabled=False,
            ),
            # Calculator bot's signature capabilities -- deterministic UK
            # pension arithmetic (app.tools.calculator), never delegated to
            # the local model. See AlmondDeveloperApp._execute_tool.
            "pension_withdrawal_tax": ToolDefinition(
                "pension_withdrawal_tax",
                "Deterministic UK pension withdrawal tax calculation",
                {
                    "type": "object",
                    "properties": {
                        "withdrawal": {"type": "string"},
                        "other_taxable_income": {"type": "string"},
                    },
                    "required": ["withdrawal"],
                },
                empty,
                "calculator:use",
            ),
            "carry_forward": ToolDefinition(
                "carry_forward",
                "Deterministic UK pension annual allowance carry-forward calculation",
                {"type": "object", "properties": {"prior_years": {"type": "array"}}},
                empty,
                "calculator:use",
            ),
            "annual_allowance": ToolDefinition(
                "annual_allowance",
                "Deterministic UK pension annual allowance position, including tapering",
                {
                    "type": "object",
                    "properties": {
                        "net_income": {"type": "string"},
                        "salary_sacrifice": {"type": "string"},
                        "relief_at_source_contributions": {"type": "string"},
                        "net_pay_contributions": {"type": "string"},
                        "employer_contributions": {"type": "string"},
                        "db_pension_input": {"type": "string"},
                        "taxable_lump_sum_death_benefit": {"type": "string"},
                    },
                    "required": ["net_income"],
                },
                empty,
                "calculator:use",
            ),
            # Drafting bot's signature capability: produces email draft text
            # only, via the shared local model -- never sends anything.
            "draft_client_email": ToolDefinition(
                "draft_client_email",
                "Draft a professional client email (subject + body); never sends it",
                {
                    "type": "object",
                    "properties": {
                        "purpose": {"type": "string"},
                        "client_context": {"type": "string"},
                        "tone": {"type": "string"},
                        "key_points": {"type": "string"},
                    },
                    "required": ["purpose"],
                },
                {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                },
                "assistant:use",
            ),
            # Coding bot's signature capability. Experimental/WIP: no file
            # modification, shell, or merge access exists yet.
            "local_development": ToolDefinition(
                "local_development",
                "Local Almond self-improvement agent (experimental, coming soon)",
                empty,
                empty,
                "assistant:use",
            ),
        }

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ValueError(f"Unknown tool: {name}") from exc

    def set_enabled(self, name: str, enabled: bool, permissions: set[str]) -> ToolDefinition:
        tool = self.get(name)
        if "tools:configure" not in permissions:
            raise PermissionError("Missing permission: tools:configure")
        tool.enabled = enabled
        return tool

    def authorize_run(self, name: str, permissions: set[str], confirmed: bool = False) -> None:
        tool = self.get(name)
        if not tool.enabled:
            raise PermissionError("Tool disabled")
        if tool.required_permission not in permissions:
            raise PermissionError(f"Missing permission: {tool.required_permission}")
        if tool.approval_required and not confirmed:
            raise PermissionError("Explicit confirmation required")
