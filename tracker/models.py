"""Data model shared by every provider."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class UsageRecord:
    """One measured free-tier metric, e.g. 'EC2 instance hours: 610 / 750 Hrs'."""

    provider: str          # aws, azure, gcp, oracle, mock-aws ...
    service: str           # EC2, Lambda, Cloud Run ...
    metric: str            # what is measured
    used: float            # how much has been used this period
    limit: float           # the free limit (0 = "any usage costs money")
    unit: str = ""
    cumulative: bool = True          # True = grows during the month and resets (hours, requests)
    forecast: Optional[float] = None # end-of-month forecast if the cloud provides one
    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.provider}|{self.service}|{self.metric}"

    @property
    def percent(self) -> float:
        if self.limit <= 0:
            return 100.0 if self.used > 0 else 0.0
        return self.used / self.limit * 100.0
