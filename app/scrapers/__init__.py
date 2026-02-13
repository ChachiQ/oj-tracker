import os
import importlib
import pkgutil
import logging

logger = logging.getLogger(__name__)

_registry = {}


def register_scraper(cls):
    """Decorator to register an OJ scraper."""
    _registry[cls.PLATFORM_NAME] = cls
    logger.info(f"Registered scraper: {cls.PLATFORM_NAME} ({cls.PLATFORM_DISPLAY})")
    return cls


def get_scraper_class(platform_name: str):
    return _registry.get(platform_name)


def get_all_scrapers():
    return dict(_registry)


def get_scraper_instance(platform_name: str, **kwargs):
    cls = _registry.get(platform_name)
    if cls is None:
        raise ValueError(f"Unknown platform: {platform_name}")
    return cls(**kwargs)


def _auto_discover():
    package_dir = os.path.dirname(__file__)
    for _, module_name, _ in pkgutil.iter_modules([package_dir]):
        if module_name not in ('base', 'common', 'rate_limiter', '__init__'):
            try:
                importlib.import_module(f'.{module_name}', package=__package__)
            except Exception as e:
                logger.error(f"Failed to load scraper module {module_name}: {e}")


_auto_discover()
