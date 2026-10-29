"""Azure provider - Consumption (Cost Management) API, which is free to call.

Tracks how much of your credit (e.g. Azure for Students) has been spent in the
current billing period, overall and per service.

Auth uses DefaultAzureCredential, so any of these work:
  * `az login` on your laptop
  * azure/login in GitHub Actions (OIDC, no secrets)
  * AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_CLIENT_SECRET env vars
"""
from __future__ import annotations

import os
from collections import defaultdict

from ..models import UsageRecord
from .base import Provider, ProviderError

_COST_FIELDS = ("cost_in_billing_currency", "cost", "pretax_cost", "cost_in_usd")
_SERVICE_FIELDS = ("meter_category", "consumed_service", "product")


def _first(obj, fields, default=None):
    for f in fields:
        value = getattr(obj, f, None)
        if value not in (None, ""):
            return value
    return default


class AzureProvider(Provider):
    name = "azure"

    def fetch(self) -> list[UsageRecord]:
        sub = os.getenv("AZURE_SUBSCRIPTION_ID") or self.settings.get("subscription_id")
        if not sub:
            raise ProviderError("Set AZURE_SUBSCRIPTION_ID (or providers.azure.subscription_id)")

        from azure.identity import DefaultAzureCredential
        from azure.mgmt.consumption import ConsumptionManagementClient

        client = ConsumptionManagementClient(DefaultAzureCredential(), sub)
        # No filter -> the API returns the current billing period.
        items = client.usage_details.list(scope=f"/subscriptions/{sub}")

        per_service: dict[str, float] = defaultdict(float)
        for item in items:
            cost = float(_first(item, _COST_FIELDS, 0) or 0)
            service = str(_first(item, _SERVICE_FIELDS, "Other"))
            per_service[service] += cost

        credit = float(self.settings.get("credit_usd", 100))
        total = sum(per_service.values())
        records = [UsageRecord(
            provider="azure", service="Subscription", metric="Credit spent",
            used=round(total, 2), limit=credit, unit="USD",
        )]
        top_n = int(self.settings.get("top_services", 5))
        for service, cost in sorted(per_service.items(), key=lambda kv: -kv[1])[:top_n]:
            if cost <= 0:
                continue
            records.append(UsageRecord(
                provider="azure", service=service, metric="Spend (share of credit)",
                used=round(cost, 2), limit=credit, unit="USD",
            ))
        return records
