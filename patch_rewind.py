import re

with open("main.py", "r") as f:
    content = f.read()

replacement = """        if problem_description.startswith("/rewind"):
            if not active_thread_id:
                print("No active project to rewind.")
                continue

            parts = problem_description.split(" ")
            if len(parts) > 1:
                try:
                    index = int(parts[1])
                    from compiler.builder import build_graph
                    graph = build_graph(active_dsl_filename)
                    thread_config = {"configurable": {"thread_id": active_thread_id}}

                    state = graph.get_state(thread_config)
                    if state and state.values:
                        status = state.values.get("status")
                        if status == "RUNNING":
                            print("Cannot rewind while project is RUNNING. Please /pause first.")
                            continue

                        # We update current_stage_index via LangGraph
                        graph.update_state(thread_config, {"current_stage_index": index})
                        print(f"[CLI] Rewound project {active_thread_id} to stage index {index}.")

                        # Note: we do not clear data because data is stage-scoped and safe.
                    else:
                        print("Project state not found.")
                except ValueError:
                    print("Invalid index. Must be an integer.")
            continue
"""

content = content.replace("""        if problem_description.startswith("/resync"):""", replacement + """\n        if problem_description.startswith("/resync"):""")

with open("main.py", "w") as f:
    f.write(content)
