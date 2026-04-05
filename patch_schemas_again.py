import re

with open("core/schemas.py", "r") as f:
    content = f.read()

replacement = """class ProjectDSL(BaseModel):
    project_name: str = Field(..., description="Name of the overall project")
    stages: List[StageDSL] = Field(..., description="List of stages in the project")
    global_budget: float = Field(..., description="Overall budget for the project in dollars")
    max_loops: int = Field(default=10, description="Maximum total evaluation loops allowed across all stages")
    thread_id: Optional[str] = None
    parent_thread_id: Optional[str] = None
    original_problem: str = Field(default="", description="The very first prompt that created this project")
    dsl_hash: str = Field(default="", description="A hash of the stages list to detect manual file edits")

from typing_extensions import TypedDict

class OverallState(TypedDict):
    project_name: str
    current_stage_index: int
    data: Dict[str, Any]
    eval_loops: Dict[str, int]
    max_loops: int
    global_budget: float
    experiment_results: Annotated[Dict[str, Any], dict_merge_or_clear]
    ingestion_path: Optional[str]
    active_pid: Optional[int]
    status: Literal["IDLE", "RUNNING", "PAUSED", "COMPLETED", "CRASHED"]
"""

content = re.sub(r'class ProjectDSL\(BaseModel\):[\s\S]*?(?=\n\n|\Z)', replacement, content)

with open("core/schemas.py", "w") as f:
    f.write(content)

with open("compiler/builder.py", "r") as f:
    content = f.read()

# Fix Indentation Error in builder.py
content = content.replace('if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}\n            data_dict[stage.stage_name]["eval_cost"] = current_cost + total_worker_cost',
                          'if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}\n            data_dict[stage.stage_name]["eval_cost"] = current_cost + total_worker_cost')

lines = content.split('\n')
for i, line in enumerate(lines):
    if 'data_dict[stage.stage_name]["output"] = worker_output' in line and "            " not in line:
        lines[i] = "            data_dict[stage.stage_name][\"output\"] = worker_output"
    if 'data_dict[stage.stage_name]["eval_cost"] = current_cost + worker_cost' in line and "            " not in line:
        lines[i] = "            data_dict[stage.stage_name][\"eval_cost\"] = current_cost + worker_cost"

with open("compiler/builder.py", "w") as f:
    f.write("\n".join(lines))
