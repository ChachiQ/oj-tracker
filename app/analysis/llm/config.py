"""
Model configuration and pricing data for all supported LLM providers.

Prices are per million tokens in USD.
"""
from __future__ import annotations

MODEL_CONFIG = {
    "claude": {
        "models": {
            "claude-haiku-4-5": {
                "input_price": 1.0,
                "output_price": 5.0,
                "tier": "basic",
            },
            "claude-opus-4-6": {
                "input_price": 5.0,
                "output_price": 25.0,
                "tier": "advanced",
            },
        }
    },
    "openai": {
        "models": {
            "gpt-4.1-mini": {
                "input_price": 0.40,
                "output_price": 1.60,
                "tier": "basic",
            },
            "gpt-5": {
                "input_price": 1.25,
                "output_price": 10.0,
                "tier": "advanced",
            },
        }
    },
    "zhipu": {
        "models": {
            "glm-5": {
                "input_price": 1.0,
                "output_price": 3.2,
                "tier": "basic",
            },
        }
    },
}


def get_model_pricing(provider: str, model: str) -> dict | None:
    """Look up pricing for a specific provider/model combination.

    Args:
        provider: Provider name (e.g. 'claude', 'openai', 'zhipu').
        model: Model identifier.

    Returns:
        Dict with 'input_price', 'output_price', and 'tier', or None if not found.
    """
    provider_config = MODEL_CONFIG.get(provider, {})
    return provider_config.get("models", {}).get(model)


def get_all_models_for_provider(provider: str) -> list[str]:
    """Return all model identifiers for a given provider."""
    provider_config = MODEL_CONFIG.get(provider, {})
    return list(provider_config.get("models", {}).keys())


def get_models_by_tier(tier: str) -> list[dict]:
    """Return all models matching a given tier across all providers.

    Args:
        tier: 'basic' or 'advanced'.

    Returns:
        List of dicts with 'provider', 'model', and pricing info.
    """
    results = []
    for provider_name, provider_config in MODEL_CONFIG.items():
        for model_name, model_info in provider_config.get("models", {}).items():
            if model_info.get("tier") == tier:
                results.append(
                    {
                        "provider": provider_name,
                        "model": model_name,
                        **model_info,
                    }
                )
    return results
