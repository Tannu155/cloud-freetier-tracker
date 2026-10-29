"""Turns raw usage into status, month-end projection and 'limit hit on' date."""
from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from .models import UsageRecord

# Alert levels from least to most severe
SEVERITY = {"PROJECTED": 1, "WARN": 2, "CRITICAL": 3, "OVER": 4}


@dataclass
class Analysis:
    record: UsageRecord
    percent: float
    status: str                      # OK | WARN | CRITICAL | OVER
    rate_per_day: Optional[float]
    projected: Optional[float]       # expected usage at month end
    limit_date: Optional[date]       # day the limit will be crossed (this month)

    @property
    def will_exceed(self) -> bool:
        r = self.record
        return r.limit > 0 and self.projected is not None and self.projected > r.limit

    @property
    def projected_percent(self) -> Optional[float]:
        if self.projected is None or self.record.limit <= 0:
            return None
        return self.projected / self.record.limit * 100


def status_for(record: UsageRecord, warn_pct: float, crit_pct: float) -> str:
    if record.limit <= 0:
        return "OVER" if record.used > 0 else "OK"
    pct = record.percent
    if pct >= 100:
        return "OVER"
    if pct >= crit_pct:
        return "CRITICAL"
    if pct >= warn_pct:
        return "WARN"
    return "OK"


def daily_rate(record: UsageRecord, today: date,
               history: list[tuple[date, float]] | None = None) -> Optional[float]:
    """Usage per day. Prefers the last ~7 days of history (trend-aware),
    falls back to the month-to-date average."""
    if not record.cumulative:
        return None
    month_points = [(d, u) for d, u in (history or [])
                    if d.year == today.year and d.month == today.month and d < today]
    if month_points:
        target = today - timedelta(days=7)
        recent = [p for p in month_points if p[0] >= target]
        base_day, base_used = recent[0] if recent else month_points[-1]
        days = (today - base_day).days
        if days > 0 and record.used >= base_used:
            return (record.used - base_used) / days
    return record.used / today.day


def analyze(record: UsageRecord, today: date, warn_pct: float = 80, crit_pct: float = 95,
            history: list[tuple[date, float]] | None = None) -> Analysis:
    status = status_for(record, warn_pct, crit_pct)
    rate = daily_rate(record, today, history)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    month_end = today.replace(day=days_in_month)

    projected = None
    if record.forecast is not None:
        projected = float(record.forecast)
    elif rate is not None:
        projected = record.used + rate * (days_in_month - today.day)

    limit_date = None
    if record.limit > 0 and record.used < record.limit and rate and rate > 0:
        days_needed = (record.limit - record.used) / rate
        candidate = today + timedelta(days=math.ceil(days_needed))
        if candidate <= month_end:
            limit_date = candidate

    return Analysis(record, record.percent, status, rate, projected, limit_date)


def alert_level(a: Analysis) -> Optional[str]:
    if a.status in ("WARN", "CRITICAL", "OVER"):
        return a.status
    if a.will_exceed and a.record.cumulative:
        return "PROJECTED"
    return None
