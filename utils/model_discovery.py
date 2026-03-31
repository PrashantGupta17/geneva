import requests
import yaml
import os

def fetch_openrouter_free_models():
    """
    Fetches available free models from OpenRouter API.
    """
    try:
        response = requests.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        models = response.json().get("data", [])

        free_models = []
        for model in models:
            # Check if model pricing is free
            pricing = model.get("pricing", {})
            prompt_price = float(pricing.get("prompt", 1.0))
            completion_price = float(pricing.get("completion", 1.0))

            if prompt_price == 0.0 and completion_price == 0.0:
                free_models.append(model["id"])

        return free_models
    except Exception as e:
        print(f"Error fetching models from OpenRouter: {e}")
        # Fallback list of known free models if API fails
        return ["openrouter/auto", "huggingface/meta-llama/Llama-2-7b-chat-hf"]

def generate_litellm_config():
    """
    Generates a litellm_config.yaml with premium and standard/free tiers.
    """
    free_models = fetch_openrouter_free_models()

    # We use a fallback if none found
    if not free_models:
        free_models = ["google/gemma-7b-it:free", "meta-llama/llama-3-8b-instruct:free"]

    config = {
        "model_list": [
            {
                "model_name": "premium-model",
                "litellm_params": {
                    "model": "gpt-4-turbo", # or any premium model
                    "api_key": "os.environ/OPENAI_API_KEY",
                },
                "model_info": {
                    "tier": "premium"
                }
            },
            {
                "model_name": "standard-model",
                "litellm_params": {
                    "model": f"openrouter/{free_models[0]}" if not free_models[0].startswith("openrouter/") else free_models[0],
                    "api_key": "os.environ/OPENROUTER_API_KEY",
                },
                "model_info": {
                    "tier": "standard"
                }
            }
        ],
        "litellm_settings": {
            "drop_params": True,
            "virtual_keys": True
        },
        "router_settings": {
            "routing_strategy": "usage-based-routing"
        }
    }

    # Add a fallback model configuration
    config["model_list"].append({
        "model_name": "fallback-free-model",
        "litellm_params": {
            "model": "openrouter/google/gemma-7b-it:free",
        },
        "model_info": {
            "tier": "free"
        }
    })

    with open("litellm_config.yaml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"Generated litellm_config.yaml with {len(free_models)} free models found.")

if __name__ == "__main__":
    generate_litellm_config()
