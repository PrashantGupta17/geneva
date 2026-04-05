import re

with open("main.py", "r") as f:
    content = f.read()

replacement = """        while True:
            decision = input("Type 'approve' to execute, 'reject' to start over, or provide feedback to refine the plan: ").strip()

            if decision.lower() == 'approve':
                print(f"\\n[CLI] Compiling and executing graph for '{active_dsl.project_name}' in background...")
                import subprocess

                # Check hash before starting
                import hashlib
                import json
                with open(active_dsl_filename, "r") as f:
                    current_file_hash = hashlib.sha256(json.dumps([s.model_dump() for s in active_dsl.stages], sort_keys=True).encode()).hexdigest()

                if current_file_hash != active_dsl.dsl_hash:
                    print("[CLI] Hash mismatch! Tampering detected. Run /resync before resuming.")
                    break

                process = subprocess.Popen(["python3", "-m", "compiler.runner", active_dsl_filename])

                print(f"\\n[CLI] Graph execution spawned in background with PID: {process.pid}")

                # The state update with PID and RUNNING is handled by the runner.py.
                break

            elif decision.lower() == 'reject':"""

content = re.sub(r'        while True:\n            decision = input\("Type \'approve\' to execute, \'reject\' to start over, or provide feedback to refine the plan: "\)\.strip\(\)\n\n            if decision\.lower\(\) == \'approve\':[\s\S]*?elif decision\.lower\(\) == \'reject\':', replacement, content)

with open("main.py", "w") as f:
    f.write(content)
