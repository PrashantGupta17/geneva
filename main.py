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

def main():
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

    while True:
        print("\n" + "="*50)

        prompt_prefix = f"[{active_thread_id}] " if active_thread_id else ""
        user_input = input(f"{prompt_prefix}Enter command (/list, /attach <id>, /fork <id>, /detach, /pause, /resume, /rewind <index>, /resync, approve, reject) or a new problem/feedback (or 'quit'): ").strip()

        if user_input.lower() == 'quit':
            for proc in active_processes:
                if proc.poll() is None:
                    print(f"Terminating background process {proc.pid}...")
                    proc.send_signal(signal.SIGTERM)
            break

        if not user_input:
            continue

        if user_input.startswith("/detach"):
            print("[CLI] Detaching. Background processes will continue running.")
            active_processes = []
            break

        if user_input.startswith("/list"):
            print("\n[CLI] Listing projects...")
            projects_dir = "projects"
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

                                graph = build_graph(filepath)
                                status, _ = get_status_from_graph(graph, t_id)
                                print(f" - {t_id} | {name} | {orig[:30]}... | Status: {status}")
                    except Exception as e:
                        pass
            continue

        if user_input.startswith("/attach"):
            parts = user_input.split(" ")
            if len(parts) > 1:
                t_id = parts[1]
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
            if len(parts) > 1:
                parent_id = parts[1]
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

            if current_file_hash != active_dsl.dsl_hash:
                print("[CLI] Hash mismatch! Tampering detected. Run /resync before resuming.")
                continue

            graph = build_graph(active_dsl_filename)
            thread_config = {"configurable": {"thread_id": active_thread_id}}
            status, pid = get_status_from_graph(graph, active_thread_id)

            if status == "PAUSED":
                if pid and psutil.pid_exists(pid):
                    graph.update_state(thread_config, {"status": "RUNNING"})
                    os.kill(pid, signal.SIGCONT)
                    print(f"Project {active_thread_id} resumed.")
                else:
                    print("Project process not found. Spawning a new background process...")
                    process = subprocess.Popen(["python3", "-m", "compiler.runner", active_dsl_filename])
                    active_processes.append(process)
            else:
                print(f"Project is not paused (status: {status}).")
            continue

        if user_input.startswith("/rewind"):
            if not active_thread_id:
                print("No active project.")
                continue
            parts = user_input.split(" ")
            if len(parts) > 1:
                try:
                    index = int(parts[1])
                    graph = build_graph(active_dsl_filename)
                    thread_config = {"configurable": {"thread_id": active_thread_id}}
                    status, pid = get_status_from_graph(graph, active_thread_id)

                    if status == "RUNNING":
                        print("Cannot rewind while project is RUNNING. Please /pause first.")
                        continue

                    if status == "PAUSED" and pid and psutil.pid_exists(pid):
                        os.kill(pid, signal.SIGKILL)
                        print("Killed paused process to avoid stale memory on resume.")

                    graph.update_state(thread_config, {"current_stage_index": index})
                    print(f"[CLI] Rewound project {active_thread_id} to stage index {index}.")
                except ValueError:
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
            print("[CLI] Project resynced to match on-disk file.")
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
                print("[CLI] ERROR: Cannot refine DSL while project is RUNNING. Please /pause first.")
                continue

            with open(active_dsl_filename, "r") as f:
                file_dsl = ProjectDSL(**yaml.safe_load(f))
                current_file_hash = hashlib.sha256(json.dumps([s.model_dump() for s in file_dsl.stages], sort_keys=True).encode()).hexdigest()
            if current_file_hash != active_dsl.dsl_hash:
                print("[CLI] Hash mismatch! Tampering detected. Run /resync before editing.")
                continue

            print(f"\n[CLI] Refining DSL based on feedback: '{user_input}'...")
            active_dsl = planner.refine_dsl(active_dsl, user_input)

            stages_dump = [s.model_dump() for s in active_dsl.stages]
            active_dsl.dsl_hash = hashlib.sha256(json.dumps(stages_dump, sort_keys=True).encode()).hexdigest()
            planner.write_dsl_to_yaml(active_dsl, filename=active_dsl_filename)
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
            active_dsl_filename = dsl_filename
            active_dsl = dsl
            print(f"\n[CLI] Initial Project DSL generated and saved to {dsl_filename}.")

if __name__ == "__main__":
    main()
