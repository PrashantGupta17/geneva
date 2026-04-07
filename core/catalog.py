from typing import Dict, Any, List

# Central source of truth for all verified Geneva OS models (April 2026 Landscape)
MODEL_CATALOG: List[Dict[str, Any]] = [
    # --- PROPRIETARY FRONTIER MODELS ---
    {
        "provider": "openai",
        "model_id": "gpt-5.4-pro-thinking",
        "pool_name": "gpt-5-pro",
        "tier": "premium",
        "web_search": True,
        "capabilities": ["text", "json", "reasoning", "web", "vision"]
    },
    {
        "provider": "openai",
        "model_id": "gpt-5.4-mini",
        "pool_name": "gpt-5-mini",
        "tier": "standard",
        "web_search": False,
        "capabilities": ["text", "json", "vision"]
    },
    {
        "provider": "openai",
        "model_id": "o1-pro",
        "pool_name": "o1",
        "tier": "premium",
        "web_search": False,
        "capabilities": ["text", "reasoning"]
    },
    {
        "provider": "openai",
        "model_id": "o1-mini",
        "pool_name": "o1",
        "tier": "standard",
        "web_search": False,
        "capabilities": ["text", "reasoning"]
    },
    {
        "provider": "anthropic",
        "model_id": "claude-opus-4.6",
        "pool_name": "claude-opus",
        "tier": "premium",
        "web_search": True, # Agentic capability
        "capabilities": ["text", "json", "reasoning", "vision", "web-ready"]
    },
    {
        "provider": "anthropic",
        "model_id": "claude-sonnet-4.6",
        "pool_name": "claude-sonnet",
        "tier": "premium",
        "web_search": False,
        "capabilities": ["text", "json", "vision", "computer-use"]
    },
    {
        "provider": "anthropic",
        "model_id": "claude-mythos-10t",
        "pool_name": "claude-mythos",
        "tier": "premium",
        "web_search": False,
        "capabilities": ["text", "reasoning"]
    },
    {
        "provider": "google",
        "model_id": "gemini-3.1-pro",
        "pool_name": "gemini-pro",
        "tier": "premium",
        "web_search": True,
        "capabilities": ["text", "json", "reasoning", "web", "vision", "video"]
    },
    {
        "provider": "google",
        "model_id": "gemini-3.1-flash",
        "pool_name": "gemini-flash",
        "tier": "standard",
        "web_search": False,
        "capabilities": ["text", "json", "speed"]
    },
    {
        "provider": "google",
        "model_id": "gemma-4-31b-dense",
        "pool_name": "gemma-4",
        "tier": "premium",
        "web_search": False,
        "capabilities": ["text", "json", "reasoning"]
    },
    {
        "provider": "xai",
        "model_id": "grok-4.20-beta",
        "pool_name": "grok-4",
        "tier": "premium",
        "web_search": True,
        "capabilities": ["text", "reasoning", "web", "real-time-x"]
    },
    {
        "provider": "xai",
        "model_id": "grok-4.20-heavy",
        "pool_name": "grok-heavy",
        "tier": "premium",
        "web_search": True,
        "capabilities": ["text", "reasoning", "agentic", "web"]
    },

    # --- NVIDIA NIM (Blackwell-Optimized) ---
    {
        "provider": "nvidia_nim",
        "model_id": "nemotron-3-ultra",
        "pool_name": "nemotron-ultra",
        "tier": "premium",
        "web_search": True,
        "capabilities": ["text", "reasoning", "web-ready", "code"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "nemotron-3-super",
        "pool_name": "nemotron-super",
        "tier": "premium",
        "web_search": False,
        "capabilities": ["text", "reasoning"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "deepseek-v4",
        "pool_name": "deepseek-v4",
        "tier": "premium",
        "web_search": False,
        "capabilities": ["text", "json", "code", "reasoning"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "deepseek-v3.2-moe",
        "pool_name": "deepseek-v3",
        "tier": "standard",
        "web_search": False,
        "capabilities": ["text", "code"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "qwen-3.5-397b",
        "pool_name": "qwen-3.5-max",
        "tier": "premium",
        "web_search": False,
        "capabilities": ["text", "json", "reasoning", "vision"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "qwen-3.5-30b-moe",
        "pool_name": "qwen-3.5-small",
        "tier": "standard",
        "web_search": False,
        "capabilities": ["text", "json"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "moonshotai/kimi-k2.5",
        "pool_name": "kimi-k2.5",
        "tier": "premium",
        "web_search": True,
        "capabilities": ["text", "json", "video", "web", "swarm"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "minimaxai/minimax-m2.5",
        "pool_name": "minimax-m2.5",
        "tier": "premium",
        "web_search": False,
        "capabilities": ["text", "json", "browsecomp"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "z.ai/glm-5",
        "pool_name": "glm-5",
        "tier": "premium",
        "web_search": True,
        "capabilities": ["text", "json", "reasoning", "web", "agentic"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "z.ai/glm-5-turbo",
        "pool_name": "glm-5",
        "tier": "premium",
        "web_search": True,
        "capabilities": ["text", "json", "reasoning", "web", "agentic"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "mistral-large-3",
        "pool_name": "mistral-large",
        "tier": "premium",
        "web_search": False,
        "capabilities": ["text", "json", "reasoning"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "llama-4-maverick-400b",
        "pool_name": "llama-4-400b",
        "tier": "premium",
        "web_search": False,
        "capabilities": ["text", "json", "reasoning"]
    },
    {
        "provider": "nvidia_nim",
        "model_id": "llama-3.1-nemotron-70b",
        "pool_name": "llama-nemotron",
        "tier": "premium",
        "web_search": True,
        "capabilities": ["text", "reasoning", "web-ready"]
    },

    # --- OPENROUTER (Free Tier Aggregator) ---
    {
        "provider": "openrouter",
        "model_id": "perplexity/sonar-large-online",
        "pool_name": "perplexity-online",
        "tier": "free",
        "web_search": True,
        "capabilities": ["text", "search", "citations", "web"]
    },
    {
        "provider": "openrouter",
        "model_id": "meta-llama/llama-3.3-70b:free",
        "pool_name": "llama-3.3-70b",
        "tier": "free",
        "web_search": False,
        "capabilities": ["text", "reasoning"]
    },
    {
        "provider": "openrouter",
        "model_id": "qwen/qwen3.6-plus:free",
        "pool_name": "qwen-3.6-plus",
        "tier": "free",
        "web_search": False,
        "capabilities": ["text", "reasoning"]
    },
    {
        "provider": "openrouter",
        "model_id": "google/gemma-3-27b-it:free",
        "pool_name": "gemma-3-27b",
        "tier": "free",
        "web_search": False,
        "capabilities": ["text", "json"]
    },
    {
        "provider": "openrouter",
        "model_id": "liquid/lfm-2.5-1.2b-thinking:free",
        "pool_name": "liquid-think",
        "tier": "free",
        "web_search": False,
        "capabilities": ["text", "reasoning"]
    },
    {
        "provider": "openrouter",
        "model_id": "openai/gpt-oss-120b:free",
        "pool_name": "gpt-oss-120b",
        "tier": "free",
        "web_search": False,
        "capabilities": ["text"]
    },

    # --- GROQ (Free Tier Aggregator) ---
    {
        "provider": "groq",
        "model_id": "llama-3.3-70b-versatile",
        "pool_name": "llama-3.3-70b",
        "tier": "free",
        "web_search": False,
        "capabilities": ["text", "reasoning"]
    },
    {
        "provider": "groq",
        "model_id": "llama-3.1-8b-instant",
        "pool_name": "llama-3.1-8b",
        "tier": "free",
        "web_search": False,
        "capabilities": ["text"]
    },
    {
        "provider": "groq",
        "model_id": "openai/gpt-oss-120b",
        "pool_name": "gpt-oss-120b",
        "tier": "free",
        "web_search": False,
        "capabilities": ["text"]
    }
]

def get_models_for_provider(provider_name: str) -> List[Dict[str, Any]]:
    return [m for m in MODEL_CATALOG if m["provider"].lower() == provider_name.lower()]

def get_model_info(provider_name: str, model_id: str) -> Optional[Dict[str, Any]]:
    for m in MODEL_CATALOG:
        if m["provider"].lower() == provider_name.lower() and m["model_id"].lower() == model_id.lower():
            return m
    return None
