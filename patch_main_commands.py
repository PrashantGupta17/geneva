import re

with open("main.py", "r") as f:
    content = f.read()

# We need to restructure the while True loop to support /list, /attach, /fork, /detach, /pause, /resume, /rewind, etc.

new_loop = """
    # Active monitoring vars
    active_thread_id = None
    active_dsl_filename = None
    active_dsl = None

    while True:
        print("\\n" + "="*50)

        prompt_prefix = f"[{active_thread_id}] " if active_thread_id else ""
        problem_description = input(f"{prompt_prefix}Enter command (/list, /attach <id>, /fork <id>, /detach, /pause, /resume, /rewind <index>, /resync) or a new problem description (or 'quit' to exit): ").strip()

        if problem_description.lower() == 'quit':
            # Handle graceful exit
            break

        if not problem_description:
            continue

        if problem_description.startswith("/list"):
            print("\\n[CLI] Listing projects...")
            # Using PostgresSaver pool if DBOS is running to fetch state
            import psycopg
            import yaml
            from core.schemas import ProjectDSL
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
                                    with psycopg.connect(dbos_url) as conn:
                                        with conn.cursor() as cur:
                                            cur.execute("SELECT checkpoint FROM checkpoints WHERE thread_id = %s ORDER BY thread_ts DESC LIMIT 1", (t_id,))
                                            row = cur.fetchone()
                                            if row:
                                                # Checkpoint is bytes containing pickled data usually or json.
                                                # To safely read just status without unpickling langgraph state, we can try to find status in the repr, but better to use Graph API if compiled, but graph is compiled per project.
                                                # We can just instantiate a generic graph or parse if we can.
                                                # For now, let's just attempt to see if it's there or use a simplified approach:
                                                # Actually, LangGraph stores checkpoints. We will fetch status via graph if we compile it.
                                                pass
                                except Exception:
                                    pass

                                print(f" - {t_id} | {name} | {orig[:30]}... | Status: ?")
                    except Exception as e:
                        print(f"Error reading {filename}: {e}")
            continue

        if problem_description.startswith("/attach"):
            parts = problem_description.split(" ")
            if len(parts) > 1:
                active_thread_id = parts[1]
                active_dsl_filename = f"projects/{active_thread_id}.yaml"
                if os.path.exists(active_dsl_filename):
                    import yaml
                    from core.schemas import ProjectDSL
                    with open(active_dsl_filename, "r") as f:
                        active_dsl = ProjectDSL(**yaml.safe_load(f))
                    print(f"\\n[CLI] Attached to project {active_thread_id}")
                else:
                    print(f"Project {active_thread_id} not found.")
                    active_thread_id = None
            continue

        if problem_description.startswith("/fork"):
            parts = problem_description.split(" ")
            if len(parts) > 1:
                parent_id = parts[1]
                parent_filename = f"projects/{parent_id}.yaml"
                if os.path.exists(parent_filename):
                    import yaml
                    from core.schemas import ProjectDSL
                    import uuid
                    import hashlib
                    import json
                    with open(parent_filename, "r") as f:
                        parent_dsl = ProjectDSL(**yaml.safe_load(f))

                    new_id = str(uuid.uuid4())
                    parent_dsl.thread_id = new_id
                    parent_dsl.parent_thread_id = parent_id

                    # Planner will process this fork
                    print(f"\\n[CLI] Forking project {parent_id} -> {new_id}")
                    # Update planner instructions
                    print("[Planner] Preserving Stage Name/Prompt/Code to maximize DBOS cache hits...")

                    planner.write_dsl_to_yaml(parent_dsl, f"projects/{new_id}.yaml")
                    active_thread_id = new_id
                    active_dsl_filename = f"projects/{new_id}.yaml"
                    active_dsl = parent_dsl
                else:
                    print(f"Parent project {parent_id} not found.")
            continue

        if problem_description.startswith("/"):
            print("Command not recognized or not implemented yet.")
            continue

        print("\\n[Planner] Querying memory for past examples and generating DSL...")
        # Reflection memory is automatically called inside generate_dsl
        dsl = planner.generate_dsl(problem_description)

        import uuid
        import hashlib
        import json

        if not dsl.thread_id:
            dsl.thread_id = str(uuid.uuid4())
        thread_id = dsl.thread_id

        # Original problem
        dsl.original_problem = problem_description

        # Compute initial hash
        stages_dump = [s.model_dump() for s in dsl.stages]
        dsl.dsl_hash = hashlib.sha256(json.dumps(stages_dump, sort_keys=True).encode()).hexdigest()

        dsl_filename = f"projects/{thread_id}.yaml"
        planner.write_dsl_to_yaml(dsl, filename=dsl_filename)

        print(f"\\n[CLI] Initial Project DSL generated and saved to {dsl_filename}.")
        print(f"[CLI] Generated Thread ID for this project: {thread_id}")

        active_thread_id = thread_id
        active_dsl_filename = dsl_filename
        active_dsl = dsl

        # Interactive loop for execution approval and refinement
"""

content = re.sub(r'    while True:\n        print\("\\n" \+ "="\*50\)\n[\s\S]*?# Interactive loop for execution approval and refinement', new_loop, content)

with open("main.py", "w") as f:
    f.write(content)
