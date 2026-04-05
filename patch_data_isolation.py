import re

with open("compiler/builder.py", "r") as f:
    content = f.read()

# Make sure we store under state["data"][stage.stage_name]
# In create_worker_node
def replace_data_dict_updates(content):
    # For data_ingestion
    content = content.replace('data_dict[f"{stage.stage_name}_output"] = content', 'if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}\n                data_dict[stage.stage_name]["output"] = content')

    # For ephemeral_code
    content = content.replace('data_dict[f"{stage.stage_name}_output"] = worker_output', 'if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}\n                data_dict[stage.stage_name]["output"] = worker_output')

    # For standard_llm
    content = content.replace('current_cost = data_dict.get(f"{stage.stage_name}_eval_cost", 0.0)', 'current_cost = data_dict.get(stage.stage_name, {}).get("eval_cost", 0.0)')
    content = content.replace('data_dict[f"{stage.stage_name}_eval_cost"] = current_cost + worker_cost', 'if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}\n            data_dict[stage.stage_name]["eval_cost"] = current_cost + worker_cost')
    content = content.replace('data_dict[f"{stage.stage_name}_output"] = worker_output', 'data_dict[stage.stage_name]["output"] = worker_output')

    return content

content = replace_data_dict_updates(content)

# In create_evaluator_node
content = content.replace('worker_output = data.get(f"{stage.stage_name}_output", "")', 'worker_output = data.get(stage.stage_name, {}).get("output", "")')
content = content.replace('data[f"{stage.stage_name}_passed"] = passes', 'if stage.stage_name not in data: data[stage.stage_name] = {}\n            data[stage.stage_name]["passed"] = passes')
content = content.replace('current_cost = data.get(f"{stage.stage_name}_eval_cost", 0.0)', 'current_cost = data.get(stage.stage_name, {}).get("eval_cost", 0.0)')
content = content.replace('data[f"{stage.stage_name}_eval_cost"] = current_cost + eval_cost', 'data[stage.stage_name]["eval_cost"] = current_cost + eval_cost')
content = content.replace('data[f"{stage.stage_name}_output"] = worker_output', 'data[stage.stage_name]["output"] = worker_output')

# In create_fanout_worker_node
content = content.replace('current_cost = data_dict.get(f"{stage.stage_name}_eval_cost", 0.0)', 'current_cost = data_dict.get(stage.stage_name, {}).get("eval_cost", 0.0)')
content = content.replace('data_dict[f"{stage.stage_name}_eval_cost"] = current_cost + total_worker_cost', 'if stage.stage_name not in data_dict: data_dict[stage.stage_name] = {}\n            data_dict[stage.stage_name]["eval_cost"] = current_cost + total_worker_cost')

# In create_routing_logic
content = content.replace('pass_flag = state.get("data", {}).get(f"{current_stage.stage_name}_passed", False)', 'pass_flag = state.get("data", {}).get(current_stage.stage_name, {}).get("passed", False)')

# In create_fanout_worker_node prepare routing call current spent
content = content.replace('current_spent = state.get("data", {}).get(f"{stage.stage_name}_eval_cost", 0.0)', 'current_spent = state.get("data", {}).get(stage.stage_name, {}).get("eval_cost", 0.0)')

# In create_worker_node prepare routing call current spent
content = content.replace('current_spent = state.get("data", {}).get(f"{stage.stage_name}_eval_cost", 0.0)', 'current_spent = state.get("data", {}).get(stage.stage_name, {}).get("eval_cost", 0.0)')


with open("compiler/builder.py", "w") as f:
    f.write(content)
