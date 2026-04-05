with open("tests/test_stabilization.py", "r") as f:
    content = f.read()

content = content.replace('result["data"].get("parallel_test_eval_cost")', 'result["data"].get("parallel_test", {}).get("eval_cost")')

with open("tests/test_stabilization.py", "w") as f:
    f.write(content)

with open("tests/test_unification.py", "r") as f:
    content = f.read()

content = content.replace('new_state["data"]["test_fanout_output"]', 'new_state["data"].get("test_fanout", {}).get("output")')
content = content.replace('assert result["data"].get("mock_stage_eval_cost") == 0.1', 'assert result["data"].get("mock_stage", {}).get("eval_cost") == 0.1')
content = content.replace('assert result["data"].get("mock_stage_output") == "mocked_output"', 'assert result["data"].get("mock_stage", {}).get("output") == "mocked_output"')

with open("tests/test_unification.py", "w") as f:
    f.write(content)
