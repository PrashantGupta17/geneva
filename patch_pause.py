import re

with open("main.py", "r") as f:
    content = f.read()

replacement = """        if problem_description.startswith("/pause"):
            if not active_thread_id:
                print("No active project to pause.")
                continue

            from compiler.builder import build_graph
            graph = build_graph(active_dsl_filename)
            thread_config = {"configurable": {"thread_id": active_thread_id}}
            state = graph.get_state(thread_config)

            if state and state.values:
                pid = state.values.get("active_pid")
                status = state.values.get("status")
                if status == "RUNNING" and pid:
                    import psutil
                    import signal
                    if psutil.pid_exists(pid):
                        os.kill(pid, signal.SIGSTOP)
                        graph.update_state(thread_config, {"status": "PAUSED"})
                        print(f"Project {active_thread_id} paused.")
                    else:
                        graph.update_state(thread_config, {"status": "CRASHED"})
                        print("Project process not found. Marked as crashed.")
                else:
                    print(f"Project is not running (status: {status}).")
            continue

        if problem_description.startswith("/resume"):
            if not active_thread_id:
                print("No active project to resume.")
                continue

            from compiler.builder import build_graph
            import hashlib
            import json
            import yaml
            from core.schemas import ProjectDSL

            with open(active_dsl_filename, "r") as f:
                file_dsl = ProjectDSL(**yaml.safe_load(f))
                current_file_hash = hashlib.sha256(json.dumps([s.model_dump() for s in file_dsl.stages], sort_keys=True).encode()).hexdigest()

            if current_file_hash != active_dsl.dsl_hash:
                print("[CLI] Hash mismatch! Tampering detected. Run /resync before resuming.")
                continue

            graph = build_graph(active_dsl_filename)
            thread_config = {"configurable": {"thread_id": active_thread_id}}
            state = graph.get_state(thread_config)

            if state and state.values:
                pid = state.values.get("active_pid")
                status = state.values.get("status")
                if status == "PAUSED" and pid:
                    import psutil
                    import signal
                    if psutil.pid_exists(pid):
                        graph.update_state(thread_config, {"status": "RUNNING"})
                        os.kill(pid, signal.SIGCONT)
                        print(f"Project {active_thread_id} resumed.")
                    else:
                        print("Project process not found. Cannot resume.")
                else:
                    print(f"Project is not paused (status: {status}).")
            continue

        if problem_description.startswith("/resync"):
            if not active_thread_id:
                print("No active project to resync.")
                continue

            import hashlib
            import json
            import yaml
            from core.schemas import ProjectDSL

            with open(active_dsl_filename, "r") as f:
                file_dsl = ProjectDSL(**yaml.safe_load(f))
                current_file_hash = hashlib.sha256(json.dumps([s.model_dump() for s in file_dsl.stages], sort_keys=True).encode()).hexdigest()

            file_dsl.dsl_hash = current_file_hash
            active_dsl = file_dsl
            planner.write_dsl_to_yaml(file_dsl, filename=active_dsl_filename)
            print("[CLI] Project resynced to match on-disk file.")
            continue
"""

content = content.replace("""        if problem_description.startswith("/fork"):""", replacement + """\n        if problem_description.startswith("/fork"):""")

with open("main.py", "w") as f:
    f.write(content)
