import re

with open("agents/planner.py", "r") as f:
    content = f.read()

replacement = """        system_prompt = f\"\"\"
You are an expert Lead Systems Architect Planner.
The user has provided feedback to refine an existing Project DSL.
Your job is to read the existing DSL and the user's natural language feedback, and output a new, updated strict JSON representation of the Project DSL.

If this is a fork (indicated by the user mentioning it or preserving cache hits), you MUST preserve Stage Name, Prompts, and Ephemeral Code EXACTLY as they are whenever possible to maximize DBOS cache hits. Only modify the components specifically requested by the user.

Current DSL:
{current_dsl.model_dump_json(indent=2)}

User Feedback:
{user_feedback}

Respond ONLY with the raw JSON object conforming exactly to the ProjectDSL schema. No markdown wrapping.
\"\"\""""

content = re.sub(r'        system_prompt = f\"\"\"\nYou are an expert Lead Systems Architect Planner.\nThe user has provided feedback to refine an existing Project DSL.[\s\S]*?Respond ONLY with the raw JSON object conforming exactly to the ProjectDSL schema\. No markdown wrapping\.\n\"\"\"', replacement, content)

with open("agents/planner.py", "w") as f:
    f.write(content)
