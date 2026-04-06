import json
from typing import Dict, Any
from core.meta_llm import invoke_master_llm
from utils.storage import resolve_payload

class CoercionError(Exception):
    pass

class DataCoercer:
    def __init__(self, model: str = "gpt-4-turbo"):
        self.model = model

    def sanitize_for_computation(self, raw_text: str, target_schema: Dict[str, Any]) -> dict:
        resolved_text = resolve_payload(raw_text)
        system_prompt = f"""
You are a strict data coercion engine.
Your objective is to extract data from the provided raw text and format it exactly according to the target schema.
You MUST return ONLY a valid JSON object matching the schema.

Target Schema:
{json.dumps(target_schema, indent=2)}
"""
        try:
            import re
            full_prompt = f"{system_prompt}\n\nUser Input: {resolved_text}"
            content = invoke_master_llm(
                prompt=full_prompt,
                response_format={"type": "json_object"}
            )

            content = re.sub(r'^```json\s*|```$', '', content, flags=re.MULTILINE).strip()
            parsed_data = json.loads(content)
            return parsed_data
        except Exception as e:
            raise CoercionError(f"Failed to coerce data: {e}")
