import re

with open("main.py", "r") as f:
    content = f.read()

replacement = """    # Active monitoring vars
    active_thread_id = None
    active_dsl_filename = None
    active_dsl = None
    active_processes = []

    while True:
        print("\\n" + "="*50)

        prompt_prefix = f"[{active_thread_id}] " if active_thread_id else ""
        problem_description = input(f"{prompt_prefix}Enter command (/list, /attach <id>, /fork <id>, /detach, /pause, /resume, /rewind <index>, /resync) or a new problem description (or 'quit' to exit): ").strip()

        if problem_description.lower() == 'quit':
            # Handle graceful exit
            import signal
            for proc in active_processes:
                if proc.poll() is None:
                    print(f"Terminating background process {proc.pid}...")
                    proc.send_signal(signal.SIGTERM)
            break

        if problem_description.startswith("/detach"):
            print("[CLI] Detaching. Background processes will continue running.")
            active_processes = []
            break
"""

content = re.sub(r'    # Active monitoring vars\n    active_thread_id = None\n    active_dsl_filename = None\n    active_dsl = None\n\n    while True:\n[\s\S]*?        if problem_description\.lower\(\) == \'quit\':\n            # Handle graceful exit\n            break', replacement, content)

replacement_approve = """                process = subprocess.Popen(["python3", "-m", "compiler.runner", active_dsl_filename])
                active_processes.append(process)"""

content = content.replace('                process = subprocess.Popen(["python3", "-m", "compiler.runner", active_dsl_filename])', replacement_approve)

with open("main.py", "w") as f:
    f.write(content)
