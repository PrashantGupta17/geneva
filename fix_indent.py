with open("compiler/builder.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'data_dict[stage.stage_name]["output"] = worker_output' in line:
        print(f"Line {i+1}: {repr(line)}")
