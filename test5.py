from compiler.builder import build_graph, OverallState
import os
import sys

# Change stage1 max_retries to 1 in DSL
os.environ["DBOS_DISABLE"] = "1"
with open("project_dsl.yaml", "w") as f:
    f.write("""
project_name: test_project_2
global_budget: 10.0
max_loops: 10
stages:
  - stage_name: "stage1"
    assigned_model_tier: "free"
    stage_budget: 2.0
    success_criteria: {}
    requires_human_approval: false
    max_retries: 1
""")

graph = build_graph("project_dsl.yaml")

initial_state: OverallState = {
    "project_name": "test_project_2",
    "current_stage_index": 0,
    "data": {},
    "eval_loops": {},
    "max_loops": 10,
    "global_budget": 10.0
}
thread_config = {"configurable": {"thread_id": "test_thread_retry"}}

for event in graph.stream(initial_state, thread_config):
    for k, v in event.items():
        print(f"Output: {k}")
