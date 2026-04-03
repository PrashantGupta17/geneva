import os
from agents.planner import PlannerAgent
from memory.reflection import ReflectionMemory
from compiler.builder import build_graph, OverallState
from dbos import DBOS

def main():
    # Make sure DBOS is running for @DBOS.step calls inside the graph
    DBOS.launch()

    planner = PlannerAgent(model="openrouter/auto") # Use whatever model is configured
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
        thread_id = str(uuid.uuid4())
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
                    "global_budget": dsl.global_budget
                }

                thread_config = {"configurable": {"thread_id": thread_id}}

                try:
                    # Sync Thread ID with DBOS workflow execution using Context/DBOS directly isn't natively exposed in
                    # graph.invoke() without custom runner. But DBOS workflow ID can be set if we wrapped the whole
                    # execution. However, we are running steps inside graph.
                    # As a workaround or basic sync, we use the same thread_id as the langgraph thread.
                    # And DBOS automatically manages its internal IDs. If we really need DBOS to use it, we could pass it.
                    final_state = graph.invoke(initial_state, thread_config)
                    print("\n[CLI] Graph execution completed successfully!")

                    print("[CLI] Storing success in Reflection Memory...")
                    memory.store_success(problem_description, dsl)

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