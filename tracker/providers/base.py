"""Base class every cloud provider implements."""
from __future__ import annotations

from datetime import date

from ..models import UsageRecord


class ProviderError(RuntimeError):
    """Raised when a provider is misconfigured or its API call fails."""


class Provider:
    name = "base"

    def __init__(self, settings: dict, today: date, root_config: dict):
        self.settings = settings or {}   # providers.<name> section of limits.yaml
        self.today = today
        self.root = root_config           # whole config (for shared values)

    def fetch(self) -> list[UsageRecord]:  # pragma: no cover - interface
        raise NotImplementedError
