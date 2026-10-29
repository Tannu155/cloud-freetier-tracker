"""Oracle Cloud provider - Usage API (free to call).

Always Free resources cost 0, so the rule is simple: any non-zero cost this
month means something is outside Always Free -> alert.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ..models import UsageRecord
from .base import Provider, ProviderError


def _oci_config(settings: dict) -> dict:
    import oci

    if os.getenv("OCI_TENANCY"):
        key = os.getenv("OCI_KEY_CONTENT", "").replace("\\n", "\n")
        config = {
            "user": os.getenv("OCI_USER"),
            "tenancy": os.getenv("OCI_TENANCY"),
            "fingerprint": os.getenv("OCI_FINGERPRINT"),
            "region": os.getenv("OCI_REGION"),
            "key_content": key,
        }
    else:
        config = oci.config.from_file(profile_name=settings.get("profile", "DEFAULT"))
    try:
        oci.config.validate_config(config)
    except Exception as exc:  # oci raises its own InvalidConfig
        raise ProviderError(f"Invalid OCI config: {exc}") from exc
    return config


class OracleProvider(Provider):
    name = "oracle"

    def fetch(self) -> list[UsageRecord]:
        import oci

        config = _oci_config(self.settings)
        client = oci.usage_api.UsageapiClient(config)

        start = datetime(self.today.year, self.today.month, 1, tzinfo=timezone.utc)
        end = datetime(self.today.year, self.today.month, self.today.day, tzinfo=timezone.utc) + timedelta(days=1)
        details = oci.usage_api.models.RequestSummarizedUsagesDetails(
            tenant_id=config["tenancy"],
            time_usage_started=start,
            time_usage_ended=end,
            granularity="DAILY",
            query_type="COST",
            group_by=["service"],
        )
        resp = client.request_summarized_usages(details)

        per_service: dict[str, float] = defaultdict(float)
        for item in resp.data.items or []:
            per_service[item.service or "Other"] += float(item.computed_amount or 0)

        allowed = float(self.settings.get("max_cost", 0))
        records = [UsageRecord(
            provider="oracle", service="Tenancy", metric="Cost outside Always Free",
            used=round(sum(per_service.values()), 2), limit=allowed, unit="USD",
        )]
        for service, cost in sorted(per_service.items(), key=lambda kv: -kv[1]):
            if cost > 0:
                records.append(UsageRecord(
                    provider="oracle", service=service, metric="Cost this month",
                    used=round(cost, 2), limit=allowed, unit="USD",
                ))
        return records
