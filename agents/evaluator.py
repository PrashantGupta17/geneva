import json
import logging
from typing import Dict, Any, Tuple
from litellm import completion_cost
from core.meta_llm import invoke_master_llm
from core.schemas import StageDSL
from utils.storage import resolve_payload

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

    def get_remaining_budget_percent(self, stage: StageDSL, current_spent: float) -> float:
        """
        Query LiteLLM (or state) for remaining budget on a Virtual Key.
        """
        remaining = stage.stage_budget - current_spent
        percent_remaining = (remaining / stage.stage_budget) * 100 if stage.stage_budget > 0 else 0
        return percent_remaining

    def prepare_routing(self, stage: StageDSL, prompt: str, current_spent: float = 0.0) -> Tuple[str, str]:
        """
        Checks budget and determines the model and prompt constraints.
        Returns: (model_tier_to_use, modified_prompt)
        """
        percent_remaining = self.get_remaining_budget_percent(stage, current_spent)
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

    def evaluate(self, stage: StageDSL, worker_output: Any) -> Tuple[bool, float]:
        """
        Evaluates the worker's output against the success criteria.
        Returns True if it passes, False otherwise.
        """
        # Phase 3: Resolve payload
        resolved_output = resolve_payload(worker_output)

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

            if stage.stage_type == "parallel_fanout":
                # Context-Safe Evaluator limit logic
                # We do not evaluate the full experiment results dump
                # Instead, check if it's a valid dictionary with keys
                system_prompt += "\nNote: This is a parallel fanout result. Simply check if the provided dictionary contains valid execution keys (provider names) and outputs."
                output_str = str(list(resolved_output.keys())) if isinstance(resolved_output, dict) else str(resolved_output)[:500]
            else:
                output_str = str(resolved_output)

            full_prompt = f"{system_prompt}\n\nWorker Output:\n{output_str}"
            content = invoke_master_llm(prompt=full_prompt)

            result = content.strip().upper()

            # Use basic matching to check if passes
            passed = ("PASS" in result)
            cost = 0.0 # Evaluator uses meta LLM which could be local CLI, cost is handled separately or 0.0

            logger.info(f"Evaluation result for '{stage.stage_name}': {'PASS' if passed else 'FAIL'}, Cost: {cost}")
            return passed, cost

        except Exception as e:
            logger.error(f"Evaluation error calling LiteLLM: {e}. Defaulting to FAIL.")
            return False, 0.0
