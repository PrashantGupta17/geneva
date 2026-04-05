import os
from agents.planner import PlannerAgent
from memory.reflection import ReflectionMemory
from compiler.builder import build_graph, OverallState
from dbos import DBOS
from core.bootstrap import auto_discover_providers

def main():
    # Bootstrap and get config
    config = auto_discover_providers()

    # Identify master planner model
    master_provider_name = config.get("master_planner")
    master_model = "openrouter/auto" # default fallback
    for p in config.get("providers", []):
        if p["name"] == master_provider_name:
            if p["type"] == "api":
                master_model = p["litellm_model_name"]
            else:
                master_model = p["name"] # Or something that planner can use

    # Make sure DBOS is running for @DBOS.step calls inside the graph
    DBOS.launch()

    planner = PlannerAgent(model=master_model)
    memory = ReflectionMemory()

    while True:
        print("\n" + "="*50)
        problem_description = input("Enter your problem description (or 'quit' to exit): ").strip()

        if problem_description.lower() == 'quit':
            break

        if not problem_description:
            continue

        print("\n[Planner] Querying memory for past examples and generating DSL...")
        # Reflection memory is automatically called inside generate_dsl
        dsl = planner.generate_dsl(problem_description)

        dsl_filename = "project_dsl.yaml"
        planner.write_dsl_to_yaml(dsl, filename=dsl_filename)

        print(f"\n[CLI] Initial Project DSL generated and saved to {dsl_filename}.")

        import uuid
        if not dsl.thread_id:
            dsl.thread_id = str(uuid.uuid4())
            planner.write_dsl_to_yaml(dsl, filename=dsl_filename)
        thread_id = dsl.thread_id
        print(f"[CLI] Generated Thread ID for this project: {thread_id}")

        # Interactive loop for execution approval and refinement
        while True:
            decision = input("Type 'approve' to execute, 'reject' to start over, or provide feedback to refine the plan: ").strip()

            if decision.lower() == 'approve':
                print(f"\n[CLI] Compiling and executing graph for '{dsl.project_name}'...")

                # Dynamically compile the graph
                graph = build_graph(dsl_filename)

                initial_state: OverallState = {
                    "project_name": dsl.project_name,
                    "current_stage_index": 0,
                    "data": {},
                    "eval_loops": {},
                    "max_loops": dsl.max_loops,
                    "global_budget": dsl.global_budget,
                    "experiment_results": [],
                    "ingestion_path": None
                }

                thread_config = {"configurable": {"thread_id": thread_id}}

                try:
                    # Sync Thread ID with DBOS workflow execution using Context/DBOS directly isn't natively exposed in
                    # graph.invoke() without custom runner. But DBOS workflow ID can be set if we wrapped the whole
                    # execution. However, we are running steps inside graph.
                    # As a workaround or basic sync, we use the same thread_id as the langgraph thread.
                    # And DBOS automatically manages its internal IDs. If we really need DBOS to use it, we could pass it.
                    current_state = initial_state
                    while True:
                        final_state = graph.invoke(current_state, thread_config)

                        # Check for interrupts
                        state_snapshot = graph.get_state(thread_config)
                        if state_snapshot and getattr(state_snapshot, "next", None):
                            # It's an interrupt
                            node_to_run = state_snapshot.next[0]
                            # Check if it's a data ingestion interrupt
                            # LangGraph allows inspecting the graph structure or state to see why it paused.
                            # In our logic, if it's data_ingestion and path is empty, we would pause.
                            # We added `interrupt_before` for human approval or data ingestion.

                            # Let's prompt the user
                            user_input = input(f"\n[Interrupt] Graph paused at '{node_to_run}'.\nEnter 'approve' to continue, or provide a file path for data ingestion: ").strip()

                            if user_input.startswith("http://") or user_input.startswith("https://") or os.path.exists(user_input):
                                graph.update_state(thread_config, {"ingestion_path": user_input})
                                current_state = None # To resume from checkpoint
                            elif user_input.lower() == 'approve':
                                current_state = None
                            else:
                                print(f"[CLI] Invalid input '{user_input}'. Must be 'approve', a valid URL, or an existing local path. Try again.")
                                # Do not set current_state to None to loop again
                        else:
                            print("\n[CLI] Graph execution completed successfully!")
                            print("[CLI] Storing success in Reflection Memory...")
                            memory.store_success(problem_description, dsl)
                            break

                except Exception as e:
                    print(f"\n[CLI] Error during graph execution: {e}")

                break

            elif decision.lower() == 'reject':
                print("[CLI] Discarding current DSL and starting over.")
                break
            else:
                print(f"\n[CLI] Refining DSL based on feedback: '{decision}'...")
                dsl = planner.refine_dsl(dsl, decision)
                planner.write_dsl_to_yaml(dsl, filename=dsl_filename)
                print(f"[CLI] DSL refined and updated in {dsl_filename}.")
                print("\n[CLI] Updated DSL structure:")
                for i, stage in enumerate(dsl.stages):
                    print(f"  Stage {i+1}: {stage.stage_name} (Model: {stage.assigned_model_tier})")

if __name__ == "__main__":
    main()