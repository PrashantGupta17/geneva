import operator
from typing import List, Dict, Any, Optional, Literal, Annotated
from pydantic import BaseModel, Field

def dict_merge_or_clear(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    # If explicitly passed an empty dictionary, clear the state.
    # Otherwise, merge keys.
    if new == {}:
        return {}
    merged = old.copy() if old else {}
    merged.update(new)
    return merged

class StageDSL(BaseModel):
    stage_name: str = Field(..., description="Name of the project stage")
    assigned_model_tier: str = Field(..., description="Tier of the model to use (e.g., 'premium', 'standard', 'free')")
    stage_budget: float = Field(..., description="Budget allocated for this stage in dollars")
    success_criteria: Dict[str, Any] = Field(..., description="Strict schema/criteria for output validation")
    requires_human_approval: bool = Field(default=False, description="Whether this stage requires human approval to proceed")
    max_retries: int = Field(default=3, description="Maximum number of retries if evaluation fails")

    stage_type: Literal["standard_llm", "parallel_fanout", "ephemeral_code", "data_ingestion"] = "standard_llm"
    capability: Literal["text", "deep_research", "image_gen", "data_processing"] = "text"
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    input_schema: Optional[Dict] = None
    ephemeral_script: Optional[str] = None
    target_providers: Optional[List[str]] = None

class ProjectDSL(BaseModel):
    project_name: str = Field(..., description="Name of the overall project")
    stages: List[StageDSL] = Field(..., description="List of stages in the project")
    global_budget: float = Field(..., description="Overall budget for the project in dollars")
    max_loops: int = Field(default=10, description="Maximum total evaluation loops allowed across all stages")
