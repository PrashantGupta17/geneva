import yaml
import json
import os
from typing import Dict, Any
from core.schemas import ProjectDSL
from memory.reflection import ReflectionMemory

# Optional litellm import to generate DSL via API
from litellm import completion

class PlannerAgent:
    def __init__(self, model: str = "gpt-4-turbo"):
        self.model = model
        self.memory = ReflectionMemory()

    def generate_dsl(self, problem_description: str) -> ProjectDSL:
        """
        Takes a natural language problem description and generates a YAML/JSON DSL defining the project.
        Automatically retrieves past examples from ChromaDB to inform layout.
        """
        past_examples = self.memory.retrieve_similar_projects(problem_description)

        system_prompt = f"""
You are an expert Lead Systems Architect Planner.
Your job is to read a natural language problem description and output a strict JSON representation of the Project DSL.

You must autonomously decide:
1. The necessary macro-stages of the project.
2. Which specific model tier to use for which stage (e.g., 'premium', 'standard', 'free'). Use premium for complex reasoning, standard/free for simple tasks.
3. How many max_retries are permitted per stage (e.g., 3).
4. Strict Pydantic-based success criteria (as JSON schema dictionaries) for each stage.
5. Whether human-in-the-loop (HITL) checkpoints are required (requires_human_approval).
6. A stage_budget for each stage, summing up to global_budget.

Here are the Pydantic schemas you must conform to:
{ProjectDSL.schema_json(indent=2)}

Past successful examples (use these to optimize your layout if provided):
{past_examples}

Respond ONLY with the raw JSON object conforming exactly to the ProjectDSL schema. No markdown wrapping.
"""

        # If API keys aren't set, we can simulate or fallback.
        # But we'll try to use litellm if possible.
        try:
            # We'll try to use a cheaper/free model to generate the DSL if standard litellm is not configured
            # But the instructions say "use litellm completion"
            response = completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Problem: {problem_description}"}
                ],
                # litellm config parameters here if needed
                response_format={ "type": "json_object" } # Assuming the model supports it
            )

            content = response.choices[0].message.content
            # Parse JSON
            dsl_dict = json.loads(content)
            # Validate with Pydantic
            dsl = ProjectDSL(**dsl_dict)
            return dsl

        except Exception as e:
            print(f"Error calling LLM for DSL generation: {e}")
            print("Falling back to a deterministic dummy DSL for testing purposes.")
            return self._fallback_dsl(problem_description)

    def _fallback_dsl(self, problem_description: str) -> ProjectDSL:
        """Fallback deterministic DSL when LLM call fails."""
        return ProjectDSL(
            project_name="fallback-project",
            global_budget=1.0,
            max_loops=10,
            stages=[
                {
                    "stage_name": "research",
                    "assigned_model_tier": "standard",
                    "stage_budget": 0.2,
                    "success_criteria": {
                        "type": "object",
                        "properties": {
                            "findings": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["findings"]
                    },
                    "requires_human_approval": False,
                    "max_retries": 3
                },
                {
                    "stage_name": "drafting",
                    "assigned_model_tier": "premium",
                    "stage_budget": 0.8,
                    "success_criteria": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "word_count": {"type": "integer"}
                        },
                        "required": ["content", "word_count"]
                    },
                    "requires_human_approval": True,
                    "max_retries": 2
                }
            ]
        )

    def write_dsl_to_yaml(self, dsl: ProjectDSL, filename: str = "project_dsl.yaml"):
        """Write the Pydantic DSL to a YAML file."""
        with open(filename, "w") as f:
            yaml.dump(dsl.model_dump(), f, sort_keys=False)
        print(f"DSL successfully written to {filename}")

if __name__ == "__main__":
    planner = PlannerAgent(model="openrouter/auto") # Use openrouter auto or any other model
    problem = "Research the latest advancements in solid state batteries and write a short summary report."
    dsl = planner.generate_dsl(problem)
    planner.write_dsl_to_yaml(dsl)
