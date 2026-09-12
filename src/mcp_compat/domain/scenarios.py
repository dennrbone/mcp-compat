"""Evolution scenario domain model."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_compat.domain.calls import ToolCall
from mcp_compat.domain.contracts import ToolContract

GroundTruth = Literal["SAFE_AUTO", "CONDITIONAL", "MUST_ABSTAIN"]
MutationFamily = Literal["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"]


class EvolutionScenario(BaseModel):
    """One labeled tool-contract evolution scenario."""

    scenario_id: str
    old_contract: ToolContract
    new_contract: ToolContract
    old_call: ToolCall
    ground_truth: GroundTruth
    mutation_family: MutationFamily
    mutation_subtype: str
    oracle: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
