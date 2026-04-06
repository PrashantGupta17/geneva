import os
import yaml
import tempfile
import subprocess
from typing import Dict, Any, Optional

def get_master_provider() -> dict:
    config_path = "geneva_config.yaml"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}
            master_name = config.get("master_planner")
            for p in config.get("providers", []):
                if p["name"] == master_name:
                    return p
    return {"type": "api", "litellm_model_name": "gpt-4-turbo"}

def invoke_master_llm(prompt: str, response_format: dict = None, provider_override: dict = None, max_tokens: int = None) -> str:
    provider = provider_override or get_master_provider()

    if provider.get("type") == "cli":
        cli_path = provider.get("absolute_path", "")
        # We simulate the exact logic from execute_external_cli
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(prompt)
            temp_path = f.name

        try:
            # We assume no tool args for the master LLM invocation based on instructions
            result = subprocess.run(
                f"{cli_path} < \"{temp_path}\"",
                shell=True,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    elif provider.get("type") == "api" or not provider:
        from litellm import completion
        model = provider.get("litellm_model_name", "gpt-4-turbo") if provider else "gpt-4-turbo"
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}]
        }
        if response_format:
            kwargs["response_format"] = response_format
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = completion(**kwargs)
        return response.choices[0].message.content
