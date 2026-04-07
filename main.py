import os
import subprocess
import signal
import psutil
import hashlib
import json
import yaml
import uuid
from dbos import DBOS

from agents.planner import PlannerAgent
from compiler.builder import build_graph, OverallState
from core.schemas import ProjectDSL
from core.bootstrap import auto_discover_providers

def get_status_from_graph(graph, thread_id):
    thread_config = {"configurable": {"thread_id": thread_id}}
    state = graph.get_state(thread_config)
    if state and state.values:
        status = state.values.get("status", "IDLE")
        active_pid = state.values.get("active_pid")
        if status == "RUNNING" and active_pid:
            if not psutil.pid_exists(active_pid):
                graph.update_state(thread_config, {"status": "CRASHED"})
                status = "CRASHED"
        return status, active_pid
    return "IDLE", None

def display_projects():
    print("\n[CLI] Listing projects...")
    projects_dir = "projects"
    if not os.path.exists(projects_dir):
        os.makedirs(projects_dir)
    indexed_projects = []
    for filename in os.listdir(projects_dir):
        if filename.endswith(".yaml"):
            try:
                filepath = os.path.join(projects_dir, filename)
                with open(filepath, "r") as f:
                    data = yaml.safe_load(f)
                    if data:
                        from core.schemas import ProjectDSL
                        dsl = ProjectDSL(**data)
                        t_id = dsl.thread_id
                        name = dsl.project_name
                        orig = dsl.original_problem

                        graph = build_graph(filepath)
                        status, _ = get_status_from_graph(graph, t_id)
                        indexed_projects.append((t_id, name, orig, status))
            except Exception:
                pass

    for i, (t_id, name, orig, status) in enumerate(indexed_projects):
        print(f" {i+1}. {name} (ID: {t_id}) | {orig[:30]}... | Status: {status}")
    return indexed_projects

def verify_api_connectivity(provider_name, model_id):
    """Utility to verify that a model is accessible and the API key is valid."""
    import litellm
    from litellm import completion
    try:
        # 1-token ping
        model_str = f"{provider_name}/{model_id}" if "/" not in model_id else model_id
        print(f"[Verifier] Pinging {model_str} to verify connectivity...")
        completion(model=model_str, messages=[{"role": "user", "content": "hi"}], max_tokens=1)
        return True, "Success"
    except Exception as e:
        return False, str(e)

def main():

    # Phase 5: Repository Hygiene
    for file in os.listdir('.'):
        if file.startswith('patch_') or file.startswith('fix_') or file.startswith('update_'):
            if file.endswith('.py'):
                try:
                    os.remove(file)
                except Exception:
                    pass
    if not os.path.exists("projects"):
        os.makedirs("projects")

    config = auto_discover_providers()
    master_provider_name = config.get("master_planner")
    master_model = "openrouter/auto"
    for p in config.get("providers", []):
        if p["name"] == master_provider_name:
            if p["type"] == "api":
                master_model = p["litellm_model_name"]
            else:
                master_model = p["name"]

    DBOS.launch()
    planner = PlannerAgent(model=master_model)

    active_thread_id = None
    active_dsl_filename = None
    active_dsl = None
    active_processes = []
    cached_graph = None
    cached_graph_filename = None

    while True:
        print("\n" + "="*50)

        if active_thread_id:
            if cached_graph_filename != active_dsl_filename:
                cached_graph = build_graph(active_dsl_filename)
                cached_graph_filename = active_dsl_filename
            status, _ = get_status_from_graph(cached_graph, active_thread_id)
            prompt_prefix = f"[{active_thread_id} | {status}] "
        else:
            prompt_prefix = ""

        user_input = input(f"{prompt_prefix}Enter command (/list, /attach, /fork, /rewind, /status, /config, /help, approve, reject) or a new problem (or 'quit'): ").strip()

        if user_input.lower() == 'quit':
            for proc in active_processes:
                if proc.poll() is None:
                    print(f"Terminating background process {proc.pid}...")
                    proc.send_signal(signal.SIGTERM)
            break

        if not user_input:
            continue

        if user_input.startswith("/help"):
            print("\n[CLI] Available Commands:")
            print("  /list              - List all projects in the workspace")
            print("  /attach [index]    - Attach to a project by its list number")
            print("  /fork [index]      - Fork a project by its list number")
            print("  /rewind [index]    - Rewind the active project to a stage number")
            print("  /status            - Get an LLM-powered summary of project progress")
            print("  /config provider add <name> - Add a new API provider and key")
            print("  /config model add           - Add and categorize a model")
            print("  /config master <name>       - Switch the Master Planner model")
            print("  /config list                - List all providers and model pools")
            print("  /pause / /resume   - Control background execution")
            print("  approve / reject   - Finalize DSL or discard context")
            continue

        if user_input.startswith("/config"):
            if user_input == "/config" or user_input == "/config ":
                print("\n[CLI] Configuration Commands:")
                print("  /config provider add <name> - Add a new API provider and key")
                print("  /config model add           - Add and categorize a model")
                print("  /config master <name>       - Switch the Master Planner model")
                print("  /config list                - List all providers and model pools")

            elif user_input.startswith("/config master "):
                new_master = user_input.replace("/config master ", "").strip()
                if os.path.exists("geneva_config.yaml"):
                    with open("geneva_config.yaml", "r") as f:
                        config = yaml.safe_load(f) or {}

                    # Verify provider exists
                    providers = config.get("providers", [])
                    if any(p["name"] == new_master for p in providers):
                        config["master_planner"] = new_master
                        with open("geneva_config.yaml", "w") as f:
                            yaml.dump(config, f, sort_keys=False)

                        # Re-initialize planner
                        master_model = "openrouter/auto"
                        for p in providers:
                            if p["name"] == new_master:
                                master_model = p.get("litellm_model_name", p["name"])
                                break
                        planner = PlannerAgent(model=master_model)
                        print(f"Master Planner switched to '{new_master}' ({master_model}).")
                    else:
                        print(f"Error: Provider '{new_master}' not found in config. Run /config provider add first.")
                else:
                    print("Error: No geneva_config.yaml found. Run bootstrap first.")

            elif user_input.startswith("/config provider add "):
                name = user_input.replace("/config provider add ", "").strip()
                if name:
                    api_key = input(f"Enter the API key for {name}: ").strip()
                    test_model = input(f"Enter a common model ID for {name} to verify (e.g. gpt-3.5-turbo): ").strip()
                    
                    # Secure Action: Set env temporarily to verify
                    os.environ[f"{name.upper()}_API_KEY"] = api_key
                    ok, err = verify_api_connectivity(name, test_model)
                    
                    if not ok:
                        print(f"Error: Could not verify connectivity for provider '{name}': {err}")
                        continue

                    # Secure Action: Write the key to the .env file
                    with open(".env", "a") as env_file:
                        env_file.write(f"\n{name.upper()}_API_KEY={api_key}\n")

                    # Update geneva_config.yaml
                    if os.path.exists("geneva_config.yaml"):
                        with open("geneva_config.yaml", "r") as config_file:
                            config = yaml.safe_load(config_file) or {}
                    else:
                        config = {}

                    if "providers" not in config:
                        config["providers"] = []
                    if "models" not in config:
                        config["models"] = []

                    # Add provider
                    if not any(p["name"] == name for p in config["providers"]):
                        config["providers"].append({"name": name, "type": "api"})

                    # Auto-add all models from catalog for this provider
                    from core.catalog import get_models_for_provider
                    catalog_models = get_models_for_provider(name)
                    
                    added_count = 0
                    for m in catalog_models:
                        if not any(existing["model_id"] == m["model_id"] and existing["provider"] == name for existing in config["models"]):
                            config["models"].append(m)
                            added_count += 1

                    with open("geneva_config.yaml", "w") as config_file:
                        yaml.dump(config, config_file, sort_keys=False)
                    
                    print(f"Provider '{name}' verified and added. Auto-configured {added_count} models from the catalog.")

            elif user_input.startswith("/config model add"):
                provider_name = input("Enter the provider name (e.g., groq): ").strip()
                model_id = input("Enter the specific model ID (e.g., llama3-70b-8192): ").strip()

                # 1. Immediate Verification
                ok, err = verify_api_connectivity(provider_name, model_id)
                if not ok:
                    print(f"Error: Could not verify model '{model_id}' on provider '{provider_name}': {err}")
                    continue

                # 2. Categorization from Catalog or Manual
                from core.catalog import get_model_info
                model_info = get_model_info(provider_name, model_id)
                
                if model_info:
                    print(f"[Catalog] Model found in official catalog. Categorizing as '{model_info['pool_name']}'.")
                    parsed_cat = model_info
                else:
                    print(f"[Catalog] Model '{model_id}' not found in official catalog.")
                    pool_name = input("Enter a generic pool name for this model (e.g. llama-3-70b): ").strip()
                    tier = input("Enter the tier (premium, standard, free): ").strip()
                    caps_str = input("Enter capabilities as a comma-separated list (e.g. text,json,reasoning,web): ").strip()
                    capabilities = [c.strip() for c in caps_str.split(",") if c.strip()]
                    
                    parsed_cat = {
                        "provider": provider_name,
                        "model_id": model_id,
                        "pool_name": pool_name,
                        "tier": tier,
                        "capabilities": capabilities,
                        "web_search": "web" in capabilities or "web_search" in capabilities
                    }

                if os.path.exists("geneva_config.yaml"):
                    with open("geneva_config.yaml", "r") as config_file:
                        config = yaml.safe_load(config_file) or {}
                else:
                    config = {}

                if "models" not in config:
                    config["models"] = []
                    
                if not any(existing["model_id"] == model_id and existing["provider"] == provider_name for existing in config["models"]):
                    config["models"].append(parsed_cat)
                    with open("geneva_config.yaml", "w") as config_file:
                        yaml.dump(config, config_file, sort_keys=False)
                    print(f"Model '{model_id}' added successfully under pool '{parsed_cat.get('pool_name', 'unknown')}'.")
                else:
                    print(f"Model '{model_id}' already exists in the configuration.")

            elif user_input.startswith("/config list"):
                if os.path.exists("geneva_config.yaml"):
                    with open("geneva_config.yaml", "r") as config_file:
                        config = yaml.safe_load(config_file) or {}

                    print("\n[CLI] Configured Providers:")
                    providers = config.get("providers", [])
                    if not providers:
                        print("  None")
                    for p in providers:
                        print(f"  - {p['name']} ({p.get('type', 'api')})")

                    print("\n[CLI] Pooled Models:")
                    models = config.get("models", [])
                    if not models:
                        print("  None (Use /config model add to add models)")
                    else:
                        models_by_pool = {}
                        for m in models:
                            pool = m.get("pool_name", "unknown")
                            if pool not in models_by_pool:
                                models_by_pool[pool] = []
                            models_by_pool[pool].append(m)

                        for pool, models_in_pool in models_by_pool.items():
                            print(f"  Pool: {pool}")
                            for m in models_in_pool:
                                caps = ", ".join(m.get("capabilities", []))
                                print(f"    - {m['provider']}/{m['model_id']} (Tier: {m.get('tier')}, Capabilities: [{caps}])")
                else:
                    print("No configuration found.")
            else:
                print("Unknown config command. Type /help for usage.")
            continue

        if user_input.startswith("/detach"):
            print("[CLI] Detaching. Background processes will continue running.")
            active_processes = []
            break

        if user_input.startswith("/list"):
            globals()["indexed_projects_cache"] = display_projects()
            continue

        if user_input.startswith("/attach"):
            parts = user_input.split(" ")
            t_id = None
            if len(parts) > 1 and not parts[1].isdigit():
                t_id = parts[1]
            else:
                if len(parts) == 1 or parts[1].isdigit():
                    globals()["indexed_projects_cache"] = display_projects()
                    idx_str = parts[1] if len(parts) > 1 else input("Enter the project number to attach: ").strip()
                    try:
                        idx = int(idx_str) - 1
                        cache = globals().get("indexed_projects_cache", [])
                        if 0 <= idx < len(cache):
                            t_id = cache[idx][0]
                        else:
                            print("Invalid project number.")
                            continue
                    except ValueError:
                        print("Please enter a valid number.")
                        continue

            if t_id:
                filepath = f"projects/{t_id}.yaml"
                if os.path.exists(filepath):
                    with open(filepath, "r") as f:
                        active_dsl = ProjectDSL(**yaml.safe_load(f))
                    active_thread_id = t_id
                    active_dsl_filename = filepath
                    print(f"\n[CLI] Attached to project {t_id}")
                else:
                    print(f"Project {t_id} not found.")
            continue

        if user_input.startswith("/fork"):
            parts = user_input.split(" ")
            parent_id = None
            if len(parts) > 1 and not parts[1].isdigit():
                parent_id = parts[1]
            else:
                if len(parts) == 1 or parts[1].isdigit():
                    globals()["indexed_projects_cache"] = display_projects()
                    idx_str = parts[1] if len(parts) > 1 else input("Enter the project number to fork: ").strip()
                    try:
                        idx = int(idx_str) - 1
                        cache = globals().get("indexed_projects_cache", [])
                        if 0 <= idx < len(cache):
                            parent_id = cache[idx][0]
                        else:
                            print("Invalid project number.")
                            continue
                    except ValueError:
                        print("Please enter a valid number.")
                        continue

            if parent_id:
                parent_filename = f"projects/{parent_id}.yaml"
                if os.path.exists(parent_filename):
                    with open(parent_filename, "r") as f:
                        parent_dsl = ProjectDSL(**yaml.safe_load(f))

                    new_id = str(uuid.uuid4())
                    parent_dsl.thread_id = new_id
                    parent_dsl.parent_thread_id = parent_id

                    print(f"\n[CLI] Forking project {parent_id} -> {new_id}")
                    print("[Planner] Preserving Stage Name/Prompt/Code to maximize DBOS cache hits...")

                    filepath = f"projects/{new_id}.yaml"
                    planner.write_dsl_to_yaml(parent_dsl, filepath)
                    active_thread_id = new_id
                    active_dsl_filename = filepath
                    active_dsl = parent_dsl
                else:
                    print(f"Parent project {parent_id} not found.")
            continue

        if user_input.startswith("/pause"):
            if not active_thread_id:
                print("No active project.")
                continue
            graph = build_graph(active_dsl_filename)
            thread_config = {"configurable": {"thread_id": active_thread_id}}
            status, pid = get_status_from_graph(graph, active_thread_id)
            if status == "RUNNING" and pid and psutil.pid_exists(pid):
                os.kill(pid, signal.SIGSTOP)
                graph.update_state(thread_config, {"status": "PAUSED"})
                print(f"Project {active_thread_id} paused.")
            else:
                print("Project is not running or process not found.")
            continue

        if user_input.startswith("/resume"):
            if not active_thread_id:
                print("No active project.")
                continue

            with open(active_dsl_filename, "r") as f:
                file_dsl = ProjectDSL(**yaml.safe_load(f))
                current_file_hash = hashlib.sha256(json.dumps([s.model_dump() for s in file_dsl.stages], sort_keys=True).encode()).hexdigest()

            graph = build_graph(active_dsl_filename)
            thread_config = {"configurable": {"thread_id": active_thread_id}}
            state = graph.get_state(thread_config)
            postgres_dsl_hash = state.values.get("dsl_hash") if state and state.values else None

            if current_file_hash != active_dsl.dsl_hash or (postgres_dsl_hash and current_file_hash != postgres_dsl_hash):
                print("[CLI] Hash mismatch! Tampering detected. Run /resync before resuming.")
                continue

            status, pid = get_status_from_graph(graph, active_thread_id)

            if status == "PAUSED":
                if pid and psutil.pid_exists(pid):
                    graph.update_state(thread_config, {"status": "RUNNING"})
                    os.kill(pid, signal.SIGCONT)
                    print(f"Project {active_thread_id} resumed.")
                else:
                    print("Project process not found. Spawning a new background process...")
                    graph.update_state(thread_config, {"active_pid": None})
                    process = subprocess.Popen(["python3", "-m", "compiler.runner", active_dsl_filename])
                    active_processes.append(process)
            else:
                print(f"Project is not paused (status: {status}).")
            continue

        if user_input.startswith("/rewind"):
            if not active_thread_id:
                print("No active project.")
                continue

            graph = build_graph(active_dsl_filename)
            thread_config = {"configurable": {"thread_id": active_thread_id}}
            status, pid = get_status_from_graph(graph, active_thread_id)

            if status == "RUNNING":
                print("Cannot rewind while project is RUNNING. Please /pause first.")
                continue

            parts = user_input.split(" ")
            index = None
            if len(parts) > 1:
                try:
                    # Standardize: Convert the 1-based input to a 0-based index.
                    index = int(parts[1]) - 1
                except ValueError:
                    print("Invalid index.")
                    continue
            else:
                state = graph.get_state(thread_config)
                print("\n[CLI] Active Stages:")
                for i, stage in enumerate(active_dsl.stages):
                    passed = False
                    if state and state.values:
                        passed = state.values.get("data", {}).get(stage.stage_name, {}).get("passed", False)
                    status_str = "PASSED" if passed else "PENDING/FAILED"
                    print(f" {i+1}. {stage.stage_name} ({status_str})")

                idx_str = input("Enter the stage number to rewind to: ").strip()
                try:
                    # Standardize: Convert the 1-based input to a 0-based index.
                    index = int(idx_str) - 1
                except ValueError:
                    print("Please enter a valid number.")
                    continue

            if index is not None:
                try:
                    if status == "PAUSED" and pid and psutil.pid_exists(pid):
                        os.kill(pid, signal.SIGKILL)
                        print("Killed paused process to avoid stale memory on resume.")

                    stage_name = active_dsl.stages[index].stage_name
                    # Secure the rewind: fetch existing data to prevent overwriting other stages
                    state = graph.get_state(thread_config)
                    current_data = state.values.get("data", {}).copy() if state and state.values else {}
                    if stage_name not in current_data:
                        current_data[stage_name] = {}
                    current_data[stage_name]["passed"] = False
                    
                    # Increment loop counter to guarantee a fresh iteration index for DBOS (forced replay)
                    current_loops = state.values.get("eval_loops", {}).copy() if state and state.values else {}
                    current_loops[stage_name] = current_loops.get(stage_name, 0) + 1
                    
                    graph.update_state(thread_config, {
                        "data": current_data, 
                        "eval_loops": current_loops,
                        "status": "PAUSED"
                    }, as_node=f"evaluator_{stage_name}")
                    print(f"[CLI] Rewound project {active_thread_id} to stage index {index+1} ({stage_name}). Status is PAUSED.")
                except (ValueError, IndexError):
                    print("Invalid index.")
            continue

        if user_input.startswith("/resync"):
            if not active_thread_id:
                continue
            with open(active_dsl_filename, "r") as f:
                file_dsl = ProjectDSL(**yaml.safe_load(f))
                current_file_hash = hashlib.sha256(json.dumps([s.model_dump() for s in file_dsl.stages], sort_keys=True).encode()).hexdigest()
            file_dsl.dsl_hash = current_file_hash
            active_dsl = file_dsl
            planner.write_dsl_to_yaml(file_dsl, filename=active_dsl_filename)

            graph = build_graph(active_dsl_filename)
            thread_config = {"configurable": {"thread_id": active_thread_id}}
            graph.update_state(thread_config, {"dsl_hash": current_file_hash})

            print("[CLI] Project resynced to match on-disk file.")
            continue

        if user_input.startswith("/status"):
            if not active_thread_id:
                print("No active project to show status for.")
                continue

            graph = build_graph(active_dsl_filename)
            thread_config = {"configurable": {"thread_id": active_thread_id}}
            state = graph.get_state(thread_config)

            if not state or not state.values:
                print("No state found for this project.")
                continue

            # Phase 4: LLM-Powered OS Dashboard
            raw_state_json = json.dumps(state.values, default=str)
            from core.meta_llm import invoke_master_llm
            prompt = f"You are the Geneva OS Dashboard. Read this raw state JSON and provide a clean, concise summary of the project's progress. List the completed stages, the currently active stage, and the total budget spent. Do not expose the raw JSON.\n\n{raw_state_json}"

            print("[Dashboard] Generating status report...")
            try:
                response = invoke_master_llm(prompt)
                print(f"\n{response}")
                print(f"\n[UI] To view visually, open LangGraph Studio and connect to local Postgres persistence for thread_id: {active_thread_id}.")
            except Exception as e:
                print(f"Failed to generate status report: {e}")
            continue

        if user_input.lower() == 'approve':
            if not active_thread_id:
                print("No active project.")
                continue

            with open(active_dsl_filename, "r") as f:
                current_file_hash = hashlib.sha256(json.dumps([s.model_dump() for s in active_dsl.stages], sort_keys=True).encode()).hexdigest()
            if current_file_hash != active_dsl.dsl_hash:
                print("[CLI] Hash mismatch! Tampering detected. Run /resync before resuming.")
                continue

            print(f"\n[CLI] Spawning execution for '{active_dsl.project_name}' in background...")
            process = subprocess.Popen(["python3", "-m", "compiler.runner", active_dsl_filename])
            active_processes.append(process)
            continue

        if user_input.lower() == 'reject':
            if active_thread_id:
                print("[CLI] Discarding current active project from context.")
                active_thread_id = None
                active_dsl_filename = None
                active_dsl = None
            continue

        # Data Ingestion handling (if it's a path or url)
        if active_thread_id and (user_input.startswith("http://") or user_input.startswith("https://") or os.path.exists(user_input)):
            graph = build_graph(active_dsl_filename)
            thread_config = {"configurable": {"thread_id": active_thread_id}}
            status, _ = get_status_from_graph(graph, active_thread_id)
            if status == "PAUSED":
                graph.update_state(thread_config, {"ingestion_path": user_input})
                print("Data ingestion path provided. Type 'approve' or '/resume' to continue.")
            else:
                print("Provided a path, but graph is not PAUSED. Assuming this is project problem description.")
                # We will just fall through to the DSL generation
            if status == "PAUSED":
                continue

        # Refine or Create new
        if active_thread_id:
            graph = build_graph(active_dsl_filename)
            status, _ = get_status_from_graph(graph, active_thread_id)
            if status == "RUNNING":
                print("Kernel Lock: Project is executing. You must run /pause before editing the DSL.")
                continue

            with open(active_dsl_filename, "r") as f:
                file_dsl = ProjectDSL(**yaml.safe_load(f))
                current_file_hash = hashlib.sha256(json.dumps([s.model_dump() for s in file_dsl.stages], sort_keys=True).encode()).hexdigest()
            if current_file_hash != active_dsl.dsl_hash:
                print("[CLI] Hash mismatch! Tampering detected. Run /resync before editing.")
                continue

            print(f"\n[CLI] Refining DSL based on feedback: '{user_input}'...")
            active_dsl = planner.refine_dsl(active_dsl, user_input, filename=active_dsl_filename)

            stages_dump = [s.model_dump() for s in active_dsl.stages]
            active_dsl.dsl_hash = hashlib.sha256(json.dumps(stages_dump, sort_keys=True).encode()).hexdigest()
            planner.write_dsl_to_yaml(active_dsl, filename=active_dsl_filename)

            thread_config = {"configurable": {"thread_id": active_thread_id}}
            graph.update_state(thread_config, {"dsl_hash": active_dsl.dsl_hash})
        else:
            print("\n[Planner] Querying memory for past examples and generating DSL...")
            dsl = planner.generate_dsl(user_input)
            if not dsl.thread_id:
                dsl.thread_id = str(uuid.uuid4())
            dsl.original_problem = user_input

            stages_dump = [s.model_dump() for s in dsl.stages]
            dsl.dsl_hash = hashlib.sha256(json.dumps(stages_dump, sort_keys=True).encode()).hexdigest()

            dsl_filename = f"projects/{dsl.thread_id}.yaml"
            planner.write_dsl_to_yaml(dsl, filename=dsl_filename)

            active_thread_id = dsl.thread_id

            # Update graph state with initial hash
            new_graph = build_graph(dsl_filename)
            new_thread_config = {"configurable": {"thread_id": active_thread_id}}
            new_graph.update_state(new_thread_config, {"dsl_hash": dsl.dsl_hash})

            active_dsl_filename = dsl_filename
            active_dsl = dsl
            print(f"\n[CLI] Initial Project DSL generated and saved to {dsl_filename}.")

if __name__ == "__main__":
    main()
