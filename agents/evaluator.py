import json
import logging
from typing import Dict, Any, Tuple
from litellm import completion, get_llm_provider
from core.schemas import StageDSL

# Setup simple logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StageAwareRouter:
    """
    Middleware/wrapper for execution nodes that manages budget via LiteLLM Virtual Keys.
    Injects TALE-style constraints or downgrades models when budget is low.
    """
    def __init__(self, config_path: str = "litellm_config.yaml"):
        self.config_path = config_path
        # In a real scenario, this would track virtual keys and their spend.
        # Since we are mocking the virtual key tracking for this example,
        # we will simulate budget tracking locally.
        self.mock_budget_spent: Dict[str, float] = {}

    def get_remaining_budget_percent(self, stage: StageDSL) -> float:
        """
        Mock function to represent querying LiteLLM for remaining budget on a Virtual Key.
        """
        # Simulated spend
        spent = self.mock_budget_spent.get(stage.stage_name, 0.0)
        remaining = stage.stage_budget - spent
        percent_remaining = (remaining / stage.stage_budget) * 100 if stage.stage_budget > 0 else 0
        return percent_remaining

    def update_budget(self, stage: StageDSL, cost: float):
        """Simulated budget update after an API call."""
        current_spent = self.mock_budget_spent.get(stage.stage_name, 0.0)
        self.mock_budget_spent[stage.stage_name] = current_spent + cost

    def prepare_routing(self, stage: StageDSL, prompt: str) -> Tuple[str, str]:
        """
        Checks budget and determines the model and prompt constraints.
        Returns: (model_tier_to_use, modified_prompt)
        """
        percent_remaining = self.get_remaining_budget_percent(stage)
        logger.info(f"Stage '{stage.stage_name}' Budget Remaining: {percent_remaining:.1f}%")

        model_tier = stage.assigned_model_tier
        modified_prompt = prompt

        if percent_remaining < 20.0:
            logger.warning(f"Low budget detected for stage '{stage.stage_name}'. Applying TALE constraints.")

            # TALE-style compression constraint injected
            constraint = "\n\nCRITICAL SYSTEM CONSTRAINT: The budget for this task is nearly exhausted. You MUST limit your reasoning. Keep your response under 150 tokens. Be extremely concise."
            modified_prompt += constraint

            # Downgrade model if it's currently premium
            if model_tier == "premium":
                logger.info("Downgrading model tier from 'premium' to 'standard' due to low budget.")
                model_tier = "standard"

        return model_tier, modified_prompt

class EvaluatorNode:
    """
    LLM-as-a-judge node that grades worker output against Pydantic success criteria.
    """
    def __init__(self, model: str = "gpt-4-turbo"):
        self.model = model # Evaluator typically uses a premium model for reliable judgment

    def evaluate(self, stage: StageDSL, worker_output: Any) -> bool:
        """
        Evaluates the worker's output against the success criteria.
        Returns True if it passes, False otherwise.
        """
        # Convert success criteria dict to a formatted string
        criteria_str = json.dumps(stage.success_criteria, indent=2)

        system_prompt = f"""
You are a strict LLM-as-a-judge Evaluator.
Your job is to grade the worker's output against the following strict JSON schema / criteria:

{criteria_str}

If the output strictly adheres to the criteria and satisfies the requirements, reply with EXACTLY "PASS".
If it fails in any way, reply with EXACTLY "FAIL".
"""
        try:
            logger.info(f"Evaluating output for stage '{stage.stage_name}'...")

            # Note: We rely on the user having litellm set up.
            # If standard litellm is not configured or fails, it throws an exception, and we return False.
            response = completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Worker Output:\n{worker_output}"}
                ],
                temperature=0.0
            )

            result = response.choices[0].message.content.strip().upper()

            passed = (result == "PASS")
            logger.info(f"Evaluation result for '{stage.stage_name}': {'PASS' if passed else 'FAIL'}")
            return passed

        except Exception as e:
            logger.error(f"Evaluation error calling LiteLLM: {e}. Defaulting to FAIL.")
            return False
