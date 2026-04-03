from compiler.builder import build_graph, OverallState
from dbos import DBOS
import os
import sys

import threading
import time

def start_dbos():
    try:
        # Some versions require it via CLI or start in background config
        DBOS.launch()
    except:
        pass

# Try dbos config locally, we might need to skip DBOS validation in this environment if no PG
os.environ["DBOS_DISABLE"] = "1"

graph = build_graph("project_dsl.yaml")

initial_state: OverallState = {
    "project_name": "test_project",
    "current_stage_index": 0,
    "data": {},
    "eval_loops": {},
    "max_loops": 10,
    "global_budget": 10.0
}
thread_config = {"configurable": {"thread_id": "test_thread_1"}}

if len(sys.argv) > 1 and sys.argv[1] == "resume":
    print("Resuming graph execution...")
    # Using None to just resume
    for event in graph.stream(None, thread_config):
        for k, v in event.items():
            print(f"Resumed Output: {k}")
else:
    print("Starting initial graph execution (will hit interrupt)...")
    for event in graph.stream(initial_state, thread_config):
        for k, v in event.items():
            print(f"Initial Output: {k}")
