with open("compiler/runner.py", "r") as f:
    content = f.read()

replacement = """        # If execution completes without interrupt
        state_snapshot = graph.get_state(thread_config)
        if state_snapshot and not getattr(state_snapshot, "next", None):
            graph.update_state(thread_config, {"status": "COMPLETED"})

            from memory.reflection import ReflectionMemory
            memory = ReflectionMemory()
            print("[Runner] Execution complete. Storing success in Reflection Memory...")
            memory.store_success(dsl.original_problem, dsl)"""

content = content.replace("""        # If execution completes without interrupt
        state_snapshot = graph.get_state(thread_config)
        if state_snapshot and not getattr(state_snapshot, "next", None):
            graph.update_state(thread_config, {"status": "COMPLETED"})""", replacement)

with open("compiler/runner.py", "w") as f:
    f.write(content)
