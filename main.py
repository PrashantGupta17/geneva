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

        print(f"\n[CLI] Project DSL generated and saved to {dsl_filename}.")
        print("[CLI] Please open LangGraph Studio now to visualize the workflow graph.")

        # Interactive loop for execution approval
        while True:
            decision = input("Type 'approve' to execute the graph, or 'reject' to start over: ").strip().lower()

            if decision == 'approve':
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

                thread_config = {"configurable": {"thread_id": "cli-thread-1"}}

                try:
                    final_state = graph.invoke(initial_state, thread_config)
                    print("\n[CLI] Graph execution completed successfully!")

                    print("[CLI] Storing success in Reflection Memory...")
                    memory.store_success(problem_description, dsl)

                except Exception as e:
                    print(f"\n[CLI] Error during graph execution: {e}")

                break

            elif decision == 'reject':
                print("[CLI] Discarding current DSL and starting over.")
                break
            else:
                print("Invalid input. Please type 'approve' or 'reject'.")

if __name__ == "__main__":
    main()