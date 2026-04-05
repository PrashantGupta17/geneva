import re

with open("main.py", "r") as f:
    content = f.read()

replacement = """        if problem_description.startswith("/list"):
            print("\\n[CLI] Listing projects...")
            # Using PostgresSaver pool if DBOS is running to fetch state
            import psycopg
            import yaml
            import pickle
            from core.schemas import ProjectDSL
            from compiler.builder import build_graph

            dbos_url = os.environ.get("DBOS_DATABASE_URL", "postgresql://postgres:password@localhost:5432/dbos")

            projects_dir = "projects"
            if not os.path.exists(projects_dir):
                print("No projects directory.")
                continue

            for filename in os.listdir(projects_dir):
                if filename.endswith(".yaml"):
                    try:
                        filepath = os.path.join(projects_dir, filename)
                        with open(filepath, "r") as f:
                            data = yaml.safe_load(f)
                            if data:
                                dsl = ProjectDSL(**data)
                                t_id = dsl.thread_id
                                name = dsl.project_name
                                orig = dsl.original_problem
                                status = "IDLE"

                                # Fetch status from postgres if available
                                try:
                                    # Create graph to use get_state and update_state directly
                                    graph = build_graph(filepath)
                                    thread_config = {"configurable": {"thread_id": t_id}}
                                    state = graph.get_state(thread_config)

                                    if state and state.values:
                                        status = state.values.get("status", "IDLE")
                                        active_pid = state.values.get("active_pid", None)

                                        # CRASH RECOVERY LOGIC
                                        if status == "RUNNING" and active_pid is not None:
                                            import psutil
                                            if not psutil.pid_exists(active_pid):
                                                status = "CRASHED"
                                                graph.update_state(thread_config, {"status": "CRASHED"})
                                except Exception as e:
                                    pass

                                print(f" - {t_id} | {name} | {orig[:30]}... | Status: {status}")
                    except Exception as e:
                        print(f"Error reading {filename}: {e}")
            continue"""

content = re.sub(r'        if problem_description\.startswith\("/list"\):[\s\S]*?            continue', replacement, content)

with open("main.py", "w") as f:
    f.write(content)
