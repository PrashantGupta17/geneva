import logging
from typing import Dict, Any
from dbos import DBOS, DBOSConfig
from compiler.builder import build_graph, OverallState

# Note: In a real project, DBOS transact decorators need proper configuration.
# We are configuring DBOS globally so @DBOS.workflow decorators function correctly.

# We will set a dummy database URL for standard open-source DBOS Transact.
# It requires postgres running. If it's not running, this will act as a mock interface or fail elegantly.
import os

DBOS.launch()

class DurabilityWorkflow:
    """
    Executes a LangGraph macro-workflow durably using DBOS Transact.
    Handles HITL (Human-in-the-loop) breakpoints so processes can pause for days
    without losing state and memory.
    """
    def __init__(self, dsl_path: str = "project_dsl.yaml"):
        self.dsl_path = dsl_path
        # Compile graph with DBOS checkpointing / durability features if needed,
        # but the request specifically says:
        # "Wrap the macro-workflow (the function iterating through the graph) with @DBOS.workflow."
        self.graph = build_graph(dsl_path)

    @DBOS.workflow()
    def run_durable_graph(self, initial_state: OverallState) -> Dict[str, Any]:
        """
        Durably iterates through the LangGraph StateGraph.
        If interrupted by a HITL requirement, DBOS reliably pauses.
        """
        print("Starting Durable Execution with DBOS...")

        # In a real environment, DBOS allows `DBOS.sleep()` or waiting on external events
        # We invoke LangGraph's native execution which will interrupt at `interrupt_before` nodes.

        # We start a streaming or sequential execution
        thread = {"configurable": {"thread_id": "1"}}

        # Due to DBOS workflow wrapping, if the application crashes here,
        # DBOS automatically restarts this workflow from the last database checkpoint.

        # Assuming we just run the graph to completion or hit a breakpoint
        final_state = self.graph.invoke(initial_state, thread)

        print("Graph execution complete or paused at HITL breakpoint.")
        return final_state

if __name__ == "__main__":
    import json
    # For testing without a real Postgres URL configured in DBOS
    # The application might throw an error if DBOS isn't properly wired to a local Postgres.
    # We will wrap in try/except for local execution safety.
    try:
        workflow = DurabilityWorkflow()
        state: OverallState = {
            "project_name": "Test Project",
            "current_stage_index": 0,
            "data": {},
            "eval_loops": 0,
            "max_loops": 10,
            "global_budget": 10.0
        }
        workflow.run_durable_graph(state)
    except Exception as e:
        print(f"DBOS Configuration or Postgres Error: {e}")
        print("Make sure PostgreSQL is running and DBOS is configured.")
