import sys
import os
import time

from compiler.builder import build_graph, load_dsl
from dbos import DBOS

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m compiler.runner <dsl_filename>")
        sys.exit(1)

    dsl_filename = sys.argv[1]

    if os.environ.get("DBOS_DISABLE") != "1":
        DBOS.launch()

    dsl = load_dsl(dsl_filename)
    thread_id = dsl.thread_id
    graph = build_graph(dsl_filename)

    thread_config = {"configurable": {"thread_id": thread_id}}

    # We retrieve current state to resume
    state_snapshot = graph.get_state(thread_config)

    # Start loop
    try:
        if state_snapshot and getattr(state_snapshot, "next", None):
             # Resuming from interrupt
             graph.invoke(None, thread_config)
        else:
            initial_state = {
                "project_name": dsl.project_name,
                "current_stage_index": 0,
                "data": {},
                "eval_loops": {},
                "max_loops": dsl.max_loops,
                "global_budget": dsl.global_budget,
                "experiment_results": {},
                "ingestion_path": None,
                "active_pid": os.getpid(),
                "status": "RUNNING"
            }
            # Instead of passing initial state directly which might override existing checkpoint
            # we invoke if there is no state.
            if not state_snapshot or not state_snapshot.values:
                graph.invoke(initial_state, thread_config)
            else:
                graph.invoke(None, thread_config)

        # If execution completes without interrupt
        state_snapshot = graph.get_state(thread_config)
        if state_snapshot and getattr(state_snapshot, "next", None):
            graph.update_state(thread_config, {"status": "PAUSED"})
            print("[Runner] Graph interrupted/paused for data ingestion or approval.")
        elif state_snapshot and not getattr(state_snapshot, "next", None):
            graph.update_state(thread_config, {"status": "COMPLETED"})

            from memory.reflection import ReflectionMemory
            memory = ReflectionMemory()
            print("[Runner] Execution complete. Storing success in Reflection Memory...")
            memory.store_success(dsl.original_problem, dsl)

    except Exception as e:
        print(f"Runner Error: {e}")
        graph.update_state(thread_config, {"status": "CRASHED"})
        sys.exit(1)

if __name__ == "__main__":
    main()
