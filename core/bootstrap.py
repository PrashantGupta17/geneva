import os
import shutil
import re
import yaml
import json
from typing import Dict, Any

def auto_discover_providers() -> Dict[str, Any]:
    config_path = "geneva_config.yaml"

    # If config exists, return it
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            if config and "providers" in config:
                return config

    print("[Bootstrap] No existing configuration found. Discovering providers...")
    discovered = []

    # API Keys discovery
    if os.environ.get("OPENAI_API_KEY"):
        discovered.append({"name": "openai", "type": "api", "litellm_model_name": "gpt-4-turbo"})
    if os.environ.get("ANTHROPIC_API_KEY"):
        discovered.append({"name": "anthropic", "type": "api", "litellm_model_name": "claude-3-opus-20240229"})
    if os.environ.get("GOOGLE_API_KEY"):
        discovered.append({"name": "gemini", "type": "api", "litellm_model_name": "gemini-pro"})

    # Local CLI discovery
    ollama_path = shutil.which("ollama")
    if ollama_path:
        discovered.append({"name": "ollama", "type": "cli", "absolute_path": ollama_path, "test_command": f"{ollama_path} --version"})

    gemini_cli_path = shutil.which("gemini")
    if gemini_cli_path:
        discovered.append({"name": "gemini_cli", "type": "cli", "absolute_path": gemini_cli_path, "test_command": f"{gemini_cli_path} --version"})

    selected_provider = None

    if not discovered:
        print("[Bootstrap] No providers discovered automatically.")
        while True:
            user_input = input("Please paste your API key or the path to your local CLI: ").strip()

            # Auto-infer
            if re.match(r"^sk-ant-", user_input):
                print("[Bootstrap] Inferred Anthropic API key.")
                os.environ["ANTHROPIC_API_KEY"] = user_input
                selected_provider = {"name": "anthropic", "type": "api", "litellm_model_name": "claude-3-opus-20240229"}
                break
            elif re.match(r"^sk-[a-zA-Z0-9]{40,}", user_input):
                print("[Bootstrap] Inferred OpenAI API key.")
                os.environ["OPENAI_API_KEY"] = user_input
                selected_provider = {"name": "openai", "type": "api", "litellm_model_name": "gpt-4-turbo"}
                break
            elif os.path.exists(user_input) and os.access(user_input, os.X_OK):
                print(f"[Bootstrap] Inferred local CLI at {user_input}.")
                name = os.path.basename(user_input)
                selected_provider = {"name": name, "type": "cli", "absolute_path": user_input, "test_command": f"{user_input} --version"}
                break
            else:
                print("[Bootstrap] Could not automatically infer provider from input. Please try again or provide a valid key/path.")
    else:
        print("[Bootstrap] Discovered the following providers:")
        for i, p in enumerate(discovered):
            print(f"  {i+1}. {p['name']} ({p['type']})")

        while True:
            choice = input(f"Select your Master Planner LLM (1-{len(discovered)}): ").strip()
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(discovered):
                    selected_provider = discovered[choice_idx]
                    break
                else:
                    print("Invalid selection. Try again.")
            except ValueError:
                print("Please enter a number.")

    # Validate the selected provider
    print(f"[Bootstrap] Validating {selected_provider['name']}...")
    if selected_provider["type"] == "api":
        from core.meta_llm import invoke_master_llm
        try:
            # 1-token completion
            invoke_master_llm(
                prompt="Hello",
                provider_override=selected_provider,
                max_tokens=1
            )
            print("[Bootstrap] Validation successful.")
        except Exception as e:
            print(f"[Bootstrap] Validation failed: {e}")
            # Still proceed for now, but in reality we might prompt again.
    else:
        import subprocess
        try:
            subprocess.run(selected_provider["test_command"], shell=True, check=True, capture_output=True)
            print("[Bootstrap] Validation successful.")

            # Phase 3: CLI Intelligence - extract flags via --help
            print(f"[Bootstrap] Extracting capabilities for CLI {selected_provider['name']}...")
            help_res = subprocess.run(f"{selected_provider['absolute_path']} --help", shell=True, capture_output=True, text=True)
            if help_res.stdout or help_res.stderr:
                from core.meta_llm import invoke_master_llm
                try:
                    help_prompt = f"Extract the supported flags and capabilities of this CLI into a JSON schema (e.g., -d / --depth, --format).\n\n{help_res.stdout}\n{help_res.stderr}"

                    schema_str = invoke_master_llm(
                        prompt=help_prompt,
                        response_format={"type": "json_object"},
                        provider_override=selected_provider
                    )

                    selected_provider["supported_args"] = json.loads(schema_str)
                    print(f"[Bootstrap] Successfully extracted supported_args.")
                except Exception as e:
                    print(f"[Bootstrap] Failed to parse --help: {e}")
        except Exception as e:
            print(f"[Bootstrap] Validation failed: {e}")

    # Save to config
    config = {
        "providers": [selected_provider],
        "master_planner": selected_provider["name"]
    }

    with open(config_path, "w") as f:
        yaml.dump(config, f, sort_keys=False)

    print(f"[Bootstrap] Configuration saved to {config_path}.")
    return config
