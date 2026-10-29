"""Provider registry. Cloud SDKs are imported lazily, so mock mode needs none of them."""
from __future__ import annotations

import importlib
from datetime import date

from .base import Provider, ProviderError

_REGISTRY = {
    "mock": ("tracker.providers.mock", "MockProvider"),
    "aws": ("tracker.providers.aws", "AwsProvider"),
    "azure": ("tracker.providers.azure", "AzureProvider"),
    "gcp": ("tracker.providers.gcp", "GcpProvider"),
    "oracle": ("tracker.providers.oracle", "OracleProvider"),
}


def available() -> list[str]:
    return list(_REGISTRY)


def get_provider(name: str, cfg: dict, today: date) -> Provider:
    if name not in _REGISTRY:
        raise ProviderError(f"Unknown provider '{name}'. Known: {', '.join(_REGISTRY)}")
    module_name, class_name = _REGISTRY[name]
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ProviderError(
            f"SDK for '{name}' is not installed ({exc}). Run: pip install -r requirements.txt"
        ) from exc
    cls = getattr(module, class_name)
    settings = (cfg.get("providers") or {}).get(name) or {}
    return cls(settings, today, cfg)


__all__ = ["Provider", "ProviderError", "get_provider", "available"]
