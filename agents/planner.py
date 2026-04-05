import yaml
import json
import os
from typing import Dict, Any
from core.schemas import ProjectDSL, StageDSL
from memory.reflection import ReflectionMemory
from core.registry import ProviderRegistry

# Optional litellm import to generate DSL via API
from litellm import completion

class PlannerAgent:
    def __init__(self, model: str = "gpt-4-turbo"):
        self.model = model
        self.memory = ReflectionMemory()
        self.registry = ProviderRegistry()

    def _load_providers(self):
        config_path = "geneva_config.yaml"
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}
                return [p["name"] for p in config.get("providers", [])]
        return []

    def generate_dsl(self, problem_description: str) -> ProjectDSL:
        past_examples = self.memory.retrieve_similar_projects(problem_description)
        providers = self._load_providers()
        providers_list = ", ".join(providers) if providers else "None found"

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

Available Providers: {providers_list}

Additional Rules:
- If the user asks for a comparison or study across multiple models, you MUST use stage_type: "parallel_fanout" and populate target_providers with available providers.
- If data requires deterministic processing (math, sorting, cleaning), you MUST use stage_type: "ephemeral_code", write the Python script in ephemeral_script, and define the input_schema.
- Your ephemeral_script MUST read input from sys.stdin (which will be a JSON string) and print the final output to sys.stdout.

Here are the Pydantic schemas you must conform to:
{ProjectDSL.schema_json(indent=2)}

Past successful examples (use these to optimize your layout if provided):
{past_examples}

Respond ONLY with the raw JSON object conforming exactly to the ProjectDSL schema. No markdown wrapping.
"""
        try:
            response = completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Problem: {problem_description}"}
                ],
                response_format={ "type": "json_object" }
            )

            content = response.choices[0].message.content
            dsl_dict = json.loads(content)
            dsl = ProjectDSL(**dsl_dict)
            return dsl

        except Exception as e:
            print(f"Error calling LLM for DSL generation: {e}")
            print("Falling back to a deterministic dummy DSL for testing purposes.")
            return self._fallback_dsl(problem_description)

    def refine_dsl(self, current_dsl: ProjectDSL, user_feedback: str) -> ProjectDSL:
        system_prompt = f"""
You are an expert Lead Systems Architect Planner.
The user has provided feedback to refine an existing Project DSL.
Your job is to read the existing DSL and the user's natural language feedback, and output a new, updated strict JSON representation of the Project DSL.

Current DSL:
{current_dsl.model_dump_json(indent=2)}

User Feedback:
{user_feedback}

Respond ONLY with the raw JSON object conforming exactly to the ProjectDSL schema. No markdown wrapping.
"""
        try:
            response = completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Please update the DSL based on my feedback."}
                ],
                response_format={ "type": "json_object" }
            )

            content = response.choices[0].message.content
            dsl_dict = json.loads(content)
            dsl = ProjectDSL(**dsl_dict)
            return dsl

        except Exception as e:
            print(f"Error calling LLM for DSL refinement: {e}")
            print("Returning the original DSL as fallback.")
            return current_dsl

    def _fallback_dsl(self, problem_description: str) -> ProjectDSL:
        return ProjectDSL(
            project_name="fallback-project",
            global_budget=1.0,
            max_loops=10,
            stages=[
                StageDSL(
                    stage_name="research",
                    assigned_model_tier="standard",
                    stage_budget=0.2,
                    success_criteria={
                        "type": "object",
                        "properties": {
                            "findings": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["findings"]
                    },
                    requires_human_approval=False,
                    max_retries=3
                ),
                StageDSL(
                    stage_name="drafting",
                    assigned_model_tier="premium",
                    stage_budget=0.8,
                    success_criteria={
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "word_count": {"type": "integer"}
                        },
                        "required": ["content", "word_count"]
                    },
                    requires_human_approval=True,
                    max_retries=2
                )
            ]
        )

    def write_dsl_to_yaml(self, dsl: ProjectDSL, filename: str = "project_dsl.yaml"):
        with open(filename, "w") as f:
            yaml.dump(dsl.model_dump(), f, sort_keys=False)
        print(f"DSL successfully written to {filename}")

if __name__ == "__main__":
    planner = PlannerAgent(model="openrouter/auto")
    problem = "Research the latest advancements in solid state batteries and write a short summary report."
    dsl = planner.generate_dsl(problem)
    planner.write_dsl_to_yaml(dsl)
