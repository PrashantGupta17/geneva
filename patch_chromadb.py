import re

with open("memory/reflection.py", "r") as f:
    content = f.read()

replacement = """        self.collection.add(
            documents=[natural_language_prompt],
            metadatas=[{"yaml_dsl": yaml_content, "project_name": final_dsl.project_name, "thread_id": final_dsl.thread_id or "", "parent_thread_id": final_dsl.parent_thread_id or ""}],
            ids=[doc_id]
        )"""

content = re.sub(r'        self\.collection\.add\(\n            documents=\[natural_language_prompt\],\n            metadatas=\[\{"yaml_dsl": yaml_content, "project_name": final_dsl\.project_name\}\],\n            ids=\[doc_id\]\n        \)', replacement, content)

with open("memory/reflection.py", "w") as f:
    f.write(content)
