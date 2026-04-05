from compiler.builder import build_graph, OverallState
import os
import sqlite3
import yaml

# Mock project_dsl.yaml
with open("project_dsl.yaml", "w") as f:
    f.write("""
project_name: test_project
global_budget: 10.0
max_loops: 10
stages:
  - stage_name: "stage1"
    assigned_model_tier: "free"
    stage_budget: 2.0
    success_criteria: {}
    requires_human_approval: false
    max_retries: 0
  - stage_name: "stage2"
    assigned_model_tier: "free"
    stage_budget: 2.0
    success_criteria: {}
    requires_human_approval: true
    max_retries: 0
  - stage_name: "stage3"
    assigned_model_tier: "free"
    stage_budget: 2.0
    success_criteria: {}
    requires_human_approval: false
    max_retries: 0
""")

print("Test setup complete.")
