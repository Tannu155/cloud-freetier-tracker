"""Mock provider: realistic fake usage so the whole project works with NO cloud account.

Values are deterministic per month (seeded random), so re-running on the same
day gives the same numbers and usage only grows during the month, like real clouds.
"""
from __future__ import annotations

import random

from ..models import UsageRecord
from .base import Provider


class MockProvider(Provider):
    name = "mock"

    def fetch(self) -> list[UsageRecord]:
        records = []
        day = self.today.day
        for m in self.root.get("mock_metrics", []):
            rate = float(m["daily_rate"])
            cumulative = bool(m.get("cumulative", True))
            seed = f"{m['provider']}|{m['service']}|{m['metric']}|{self.today:%Y-%m}"
            rng = random.Random(seed)
            daily = [rate * rng.uniform(0.6, 1.4) for _ in range(31)]

            if cumulative:
                used = sum(daily[:day])          # resets every month
            else:
                used = float(m.get("base", 0)) + rate * day  # e.g. storage slowly growing

            records.append(UsageRecord(
                provider=f"mock-{m['provider']}",
                service=m["service"],
                metric=m["metric"],
                used=round(used, 3),
                limit=float(m["limit"]),
                unit=m.get("unit", ""),
                cumulative=cumulative,
                note="simulated data",
            ))
        return records
