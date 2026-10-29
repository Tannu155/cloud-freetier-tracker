"""SQLite storage: daily usage history + which alerts were already sent."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from .analyzer import Analysis
from .models import UsageRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    day          TEXT NOT NULL,
    provider     TEXT NOT NULL,
    service      TEXT NOT NULL,
    metric       TEXT NOT NULL,
    used         REAL NOT NULL,
    limit_value  REAL NOT NULL,
    unit         TEXT,
    percent      REAL,
    status       TEXT,
    projected    REAL,
    limit_date   TEXT,
    note         TEXT,
    PRIMARY KEY (day, provider, service, metric)
);
CREATE TABLE IF NOT EXISTS alerts (
    month    TEXT NOT NULL,
    provider TEXT NOT NULL,
    service  TEXT NOT NULL,
    metric   TEXT NOT NULL,
    level    TEXT NOT NULL,
    sent_at  TEXT NOT NULL,
    PRIMARY KEY (month, provider, service, metric, level)
);
"""


class Storage:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def save(self, day: date, a: Analysis) -> None:
        r = a.record
        self.conn.execute(
            """INSERT OR REPLACE INTO usage
               (day, provider, service, metric, used, limit_value, unit, percent,
                status, projected, limit_date, note)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (day.isoformat(), r.provider, r.service, r.metric, r.used, r.limit, r.unit,
             round(a.percent, 2), a.status,
             None if a.projected is None else round(a.projected, 3),
             a.limit_date.isoformat() if a.limit_date else None, r.note),
        )
        self.conn.commit()

    def history(self, r: UsageRecord, today: date) -> list[tuple[date, float]]:
        start = today.replace(day=1).isoformat()
        rows = self.conn.execute(
            """SELECT day, used FROM usage
               WHERE provider=? AND service=? AND metric=? AND day>=? AND day<?
               ORDER BY day""",
            (r.provider, r.service, r.metric, start, today.isoformat()),
        ).fetchall()
        return [(date.fromisoformat(d), u) for d, u in rows]

    def alert_sent(self, month: str, r: UsageRecord, level: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM alerts WHERE month=? AND provider=? AND service=? AND metric=? AND level=?",
            (month, r.provider, r.service, r.metric, level),
        ).fetchone()
        return row is not None

    def mark_alert(self, month: str, r: UsageRecord, level: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO alerts VALUES (?,?,?,?,?,?)",
            (month, r.provider, r.service, r.metric, level,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        self.conn.commit()

    def latest(self) -> list[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        try:
            return self.conn.execute(
                "SELECT * FROM usage WHERE day=(SELECT MAX(day) FROM usage) ORDER BY percent DESC"
            ).fetchall()
        finally:
            self.conn.row_factory = None
