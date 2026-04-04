import os
import yaml
from core.registry import ProviderRegistry

def run_setup():
    print("Welcome to Geneva Setup Wizard!")

    config = {}

    # Global storage preferences
    print("\n--- Storage Configuration ---")
    print("Select global storage preference:")
    print("1. LocalStorage")
    print("2. GoogleDrive (Stub)")
    choice = input("Enter choice (1/2): ").strip()

    if choice == "2":
        storage_type = "GoogleDrive"
        storage_path = input("Enter the absolute path to your local synced Google Drive folder: ").strip()
    else:
        storage_type = "LocalStorage"
        storage_path = input("Enter the path for local storage (default: ./storage): ").strip()
        if not storage_path:
            storage_path = "./storage"

    # Verify storage accessibility
    print("Verifying storage accessibility...")
    try:
        os.makedirs(storage_path, exist_ok=True)
        canary_file = os.path.join(storage_path, ".canary")
        with open(canary_file, "w") as f:
            f.write("test")
        with open(canary_file, "r") as f:
            content = f.read()
        if content != "test":
            raise ValueError("Read mismatch")
        os.remove(canary_file)
        print("Storage verification: Success")
        config["storage"] = {
            "type": storage_type,
            "path": storage_path
        }
    except Exception as e:
        print(f"Storage verification: Failed - {e}")
        return

    # Model providers
    print("\n--- Model Providers Configuration ---")
    registry = ProviderRegistry()
    providers_config = []

    while True:
        print("Add a model provider:")
        print("1. API Provider (e.g., OpenAI, Anthropic via LiteLLM)")
        print("2. CLI Provider (e.g., Gemini CLI)")
        print("3. Done adding providers")
        choice = input("Enter choice (1/2/3): ").strip()

        if choice == "1":
            name = input("Enter provider name: ").strip()
            model_name = input("Enter LiteLLM model name (e.g., gpt-4-turbo): ").strip()
            registry.add_api_provider(name, model_name)
            providers_config.append({"name": name, "type": "api", "litellm_model_name": model_name})
            print(f"Added API Provider: {name}")

        elif choice == "2":
            name = input("Enter provider name (e.g., Gemini CLI): ").strip()
            path = input("Enter absolute path to CLI executable: ").strip()
            test_cmd = input("Enter test command (e.g., gemini --version): ").strip()
            registry.add_cli_provider(name, path, test_cmd)

            print(f"Verifying {name}...")
            if registry.verify_provider(name):
                print(f"Verification: Success")
                providers_config.append({"name": name, "type": "cli", "absolute_path": path, "test_command": test_cmd})
            else:
                print(f"Verification: Failed. Could not execute test command.")

        elif choice == "3":
            break
        else:
            print("Invalid choice.")

    config["providers"] = providers_config

    # Save to config
    config_file = "geneva_config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"\nConfiguration saved to {config_file}.")
    print("IMPORTANT: Please manually add any sensitive API keys to your .env file.")
    print("Example:\nOPENAI_API_KEY=your_key_here\nOPENROUTER_API_KEY=your_key_here")

if __name__ == "__main__":
    run_setup()
