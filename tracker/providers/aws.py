"""AWS provider - uses ONLY free APIs.

* freetier:GetAccountPlanState  -> remaining credits on the new (2025+) AWS Free plan
* freetier:GetFreeTierUsage     -> per-service usage vs free limit (legacy free tier accounts)

We deliberately do NOT call Cost Explorer: its API is charged per request.
"""
from __future__ import annotations

from ..models import UsageRecord
from .base import Provider, ProviderError


class AwsProvider(Provider):
    name = "aws"

    def fetch(self) -> list[UsageRecord]:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        # The Free Tier API lives in us-east-1 regardless of where your resources are.
        session = boto3.session.Session(
            profile_name=self.settings.get("profile") or None,
            region_name="us-east-1",
        )
        client = session.client("freetier")

        records: list[UsageRecord] = []
        problems: list[str] = []

        for fetcher in (self._credits, self._usage):
            try:
                records.extend(fetcher(client))
            except (ClientError, BotoCoreError, AttributeError) as exc:
                problems.append(f"{fetcher.__name__.strip('_')}: {exc}")

        if not records and problems:
            raise ProviderError("; ".join(problems))
        return records

    def _credits(self, client) -> list[UsageRecord]:
        """New AWS Free plan: track credits used out of your starting credits."""
        if not hasattr(client, "get_account_plan_state"):
            return []  # older boto3
        resp = client.get_account_plan_state()
        if resp.get("accountPlanType") != "FREE":
            return []
        remaining = float((resp.get("accountPlanRemainingCredits") or {}).get("amount", 0))
        starting = float(self.settings.get("starting_credits_usd", 100))
        expires = resp.get("accountPlanExpirationDate")
        note = f"plan expires {expires:%d %b %Y}" if hasattr(expires, "strftime") else ""
        return [UsageRecord(
            provider="aws", service="Free plan", metric="Credits used",
            used=round(max(starting - remaining, 0.0), 2), limit=starting, unit="USD",
            note=note,
        )]

    def _usage(self, client) -> list[UsageRecord]:
        """Legacy 12-month / always-free usage, with AWS's own forecast."""
        records, kwargs = [], {}
        while True:
            resp = client.get_free_tier_usage(**kwargs)
            for item in resp.get("freeTierUsages", []):
                limit = float(item.get("limit") or 0)
                if limit <= 0:
                    continue
                records.append(UsageRecord(
                    provider="aws",
                    service=item.get("service", "Unknown"),
                    metric=item.get("description") or item.get("usageType", "usage"),
                    used=float(item.get("actualUsageAmount") or 0),
                    limit=limit,
                    unit=item.get("unit", ""),
                    forecast=item.get("forecastedUsageAmount"),
                    note=item.get("freeTierType", ""),
                ))
            token = resp.get("nextToken")
            if not token:
                return records
            kwargs = {"nextToken": token}
