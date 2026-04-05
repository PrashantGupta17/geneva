import re

with open("main.py", "r") as f:
    content = f.read()

# Make sure 'projects/' dir is created in main
main_start = "def main():"
main_start_replacement = """def main():
    if not os.path.exists("projects"):
        os.makedirs("projects")"""

content = content.replace(main_start, main_start_replacement)

# change "project_dsl.yaml" to f"projects/{thread_id}.yaml"
# First we need to get the thread ID before saving the initial DSL. But planner.generate_dsl might not have it.
# Actually, the original code does:
# dsl_filename = "project_dsl.yaml"
# planner.write_dsl_to_yaml(dsl, filename=dsl_filename)
# import uuid
# if not dsl.thread_id:
#     dsl.thread_id = str(uuid.uuid4())
#     planner.write_dsl_to_yaml(dsl, filename=dsl_filename)

replacement = """        import uuid
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
        print(f"[CLI] Generated Thread ID for this project: {thread_id}")"""

content = re.sub(r'        dsl_filename = "project_dsl\.yaml"\n[\s\S]*?print\(f"\[CLI\] Generated Thread ID for this project: \{thread_id\}"\)', replacement, content)


with open("main.py", "w") as f:
    f.write(content)
