"""GCP provider - reads the Cloud Billing export in BigQuery.

Cost safety: every query sets maximum_bytes_billed, so BigQuery refuses to run
(instead of charging you) if a query would ever scan more than the cap.
A personal billing table is tiny and stays far inside BigQuery's free quota.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict

from ..models import UsageRecord
from .base import Provider, ProviderError

_TABLE_RE = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")

QUERY = """
SELECT
  service.description AS service,
  sku.description AS sku,
  SUM(usage.amount_in_pricing_units) AS amount,
  ANY_VALUE(usage.pricing_unit) AS unit,
  SUM(cost) AS cost,
  SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS credits
FROM `{table}`
WHERE invoice.month = @month
GROUP BY service, sku
"""


class GcpProvider(Provider):
    name = "gcp"

    def fetch(self) -> list[UsageRecord]:
        table = os.getenv("GCP_BILLING_TABLE") or self.settings.get("billing_table", "")
        if not _TABLE_RE.match(table or ""):
            raise ProviderError(
                "Set GCP_BILLING_TABLE to 'project.dataset.table' (your billing export table)"
            )

        from google.cloud import bigquery

        project = os.getenv("GCP_PROJECT_ID") or self.settings.get("project_id") or table.split(".")[0]
        client = bigquery.Client(project=project)
        max_bytes = int(self.settings.get("max_bytes_billed", 100 * 1024 * 1024))  # 100 MB
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("month", "STRING", f"{self.today:%Y%m}")],
            maximum_bytes_billed=max_bytes,
        )
        rows = list(client.query(QUERY.format(table=table), job_config=job_config).result())

        records: list[UsageRecord] = []
        net_cost = sum(float(r.cost or 0) + float(r.credits or 0) for r in rows)
        records.append(UsageRecord(
            provider="gcp", service="Billing", metric="Net cost after credits",
            used=round(max(net_cost, 0.0), 2), limit=float(self.settings.get("max_net_cost", 0)),
            unit="USD",
        ))

        # Compare selected SKUs against their free-tier quantity from limits.yaml
        amounts: dict[int, float] = defaultdict(float)
        rules = self.settings.get("skus") or []
        for r in rows:
            for i, rule in enumerate(rules):
                if rule.get("service", "").lower() not in (r.service or "").lower():
                    continue
                if rule.get("sku_contains", "").lower() not in (r.sku or "").lower():
                    continue
                amounts[i] += float(r.amount or 0) * float(rule.get("multiplier", 1))
        for i, rule in enumerate(rules):
            records.append(UsageRecord(
                provider="gcp", service=rule["service"], metric=rule["label"],
                used=round(amounts.get(i, 0.0), 3), limit=float(rule["limit"]),
                unit=rule.get("unit", ""),
            ))
        return records
