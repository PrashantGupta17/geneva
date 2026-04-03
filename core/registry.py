import subprocess
from typing import Dict, Any, Optional

class ProviderRegistry:
    def __init__(self):
        # Maps provider name -> provider info
        self.providers: Dict[str, Dict[str, Any]] = {}

    def add_api_provider(self, name: str, litellm_model_name: str):
        self.providers[name] = {
            "type": "api",
            "litellm_model_name": litellm_model_name
        }

    def add_cli_provider(self, name: str, absolute_path: str, test_command: str):
        self.providers[name] = {
            "type": "cli",
            "absolute_path": absolute_path,
            "test_command": test_command
        }

    def get_provider(self, name: str) -> Optional[Dict[str, Any]]:
        return self.providers.get(name)

    def verify_provider(self, name: str) -> bool:
        provider = self.get_provider(name)
        if not provider:
            return False

        if provider["type"] == "api":
            # API providers are assumed valid for this scope, or handled by litellm config
            return True

        elif provider["type"] == "cli":
            # Execute the test command and check for a 0 exit code
            try:
                # We split the command or use shell=True depending on requirement,
                # but standard practice is to use shell=True for full commands
                # or split if it's simpler. Let's use shell=True for convenience
                # if the test command is a full command string like `gemini --version`.
                result = subprocess.run(
                    provider["test_command"],
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                return result.returncode == 0
            except Exception:
                return False

        return False
