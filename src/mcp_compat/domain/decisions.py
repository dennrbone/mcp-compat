"""System decisions; benchmark oracle data must not be supplied here."""

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from mcp_compat.domain.calls import ToolCall


class MigrationDecision(BaseModel):
    action: Literal["EXECUTE", "ABSTAIN"]
    adapted_call: ToolCall | None = None
    reasons: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        if (self.action == "EXECUTE") != (self.adapted_call is not None):
            raise ValueError("EXECUTE requires adapted_call; ABSTAIN requires null")
        return self
