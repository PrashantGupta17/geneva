with open("tests/test_unification.py", "r") as f:
    content = f.read()

content = content.replace('new_state["data"]["test_fanout_passed"]', 'new_state["data"].get("test_fanout", {}).get("passed")')

with open("tests/test_unification.py", "w") as f:
    f.write(content)
