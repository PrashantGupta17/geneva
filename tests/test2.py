from agents.planner import PlannerAgent
from core.schemas import ProjectDSL, StageDSL
import os

planner = PlannerAgent(model="openrouter/auto")
# First create a basic DSL
dsl = ProjectDSL(
    project_name="Test Project",
    global_budget=10.0,
    max_loops=10,
    stages=[
        StageDSL(stage_name="Stage 1", assigned_model_tier="free", stage_budget=5.0, success_criteria={}, requires_human_approval=False, max_retries=3),
        StageDSL(stage_name="Stage 2", assigned_model_tier="free", stage_budget=5.0, success_criteria={}, requires_human_approval=False, max_retries=3)
    ]
)

# Refine
new_dsl = planner.refine_dsl(dsl, "Add a 3rd stage for QA.")
print(f"Number of stages: {len(new_dsl.stages)}")
if len(new_dsl.stages) >= 3:
    print("Test passed: Planner successfully refined DSL with additional stage.")
else:
    print("Test failed: Planner did not add a 3rd stage.")
