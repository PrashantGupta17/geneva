from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class StageDSL(BaseModel):
    stage_name: str = Field(..., description="Name of the project stage")
    assigned_model_tier: str = Field(..., description="Tier of the model to use (e.g., 'premium', 'standard', 'free')")
    stage_budget: float = Field(..., description="Budget allocated for this stage in dollars")
    success_criteria: Dict[str, Any] = Field(..., description="Strict schema/criteria for output validation")
    requires_human_approval: bool = Field(default=False, description="Whether this stage requires human approval to proceed")
    max_retries: int = Field(default=3, description="Maximum number of retries if evaluation fails")

class ProjectDSL(BaseModel):
    project_name: str = Field(..., description="Name of the overall project")
    stages: List[StageDSL] = Field(..., description="List of stages in the project")
    global_budget: float = Field(..., description="Overall budget for the project in dollars")
    max_loops: int = Field(default=10, description="Maximum total evaluation loops allowed across all stages")
