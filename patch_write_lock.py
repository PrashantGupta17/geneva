import re

with open("main.py", "r") as f:
    content = f.read()

replacement = """            elif decision.lower() == 'reject':
                print("[CLI] Discarding current DSL and starting over.")
                break
            else:
                from compiler.builder import build_graph
                graph = build_graph(active_dsl_filename)
                thread_config = {"configurable": {"thread_id": active_thread_id}}
                state = graph.get_state(thread_config)

                status = "IDLE"
                if state and state.values:
                    status = state.values.get("status", "IDLE")

                if status == "RUNNING":
                    print("[CLI] ERROR: Cannot refine or edit DSL while project is RUNNING. Please /pause first.")
                    continue

                import hashlib
                import json
                with open(active_dsl_filename, "r") as f:
                    import yaml
                    from core.schemas import ProjectDSL
                    file_dsl = ProjectDSL(**yaml.safe_load(f))
                    current_file_hash = hashlib.sha256(json.dumps([s.model_dump() for s in file_dsl.stages], sort_keys=True).encode()).hexdigest()

                if current_file_hash != active_dsl.dsl_hash:
                    print("[CLI] Hash mismatch! Tampering detected. Run /resync before editing.")
                    continue

                print(f"\\n[CLI] Refining DSL based on feedback: '{decision}'...")"""

content = re.sub(r'            elif decision\.lower\(\) == \'reject\':\n                print\("\[CLI\] Discarding current DSL and starting over\."\)\n                break\n            else:\n                print\(f"\\n\[CLI\] Refining DSL based on feedback: \'\{decision\}\'\.\.\."\)', replacement, content)

with open("main.py", "w") as f:
    f.write(content)
