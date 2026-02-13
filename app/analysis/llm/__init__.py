"""
LLM provider registry and factory.

Supports multiple LLM backends (Claude, OpenAI, Zhipu) via a plugin architecture.
Providers are auto-discovered from modules in this package.
"""

import logging

logger = logging.getLogger(__name__)

_providers = {}


def register_provider(cls):
    """Decorator to register an LLM provider class."""
    _providers[cls.PROVIDER_NAME] = cls
    return cls


def get_provider(name: str, api_key: str = None):
    """Get an instantiated LLM provider by name.

    Args:
        name: Provider name (e.g. 'claude', 'openai', 'zhipu').
        api_key: Optional API key override.

    Returns:
        An instance of the requested provider.

    Raises:
        ValueError: If the provider name is not registered.
    """
    cls = _providers.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown LLM provider: {name}. Available: {list(_providers.keys())}"
        )
    return cls(api_key=api_key)


def get_available_providers():
    """Return a dict of all registered provider classes."""
    return dict(_providers)


# Auto-discover providers
import importlib
import pkgutil
import os

_pkg_dir = os.path.dirname(__file__)
for _, mod_name, _ in pkgutil.iter_modules([_pkg_dir]):
    if mod_name not in ("base", "config", "__init__"):
        try:
            importlib.import_module(f".{mod_name}", package=__package__)
        except Exception as e:
            logger.warning(f"Failed to load LLM provider {mod_name}: {e}")
