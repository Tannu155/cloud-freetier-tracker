"""Telegram notifications (free). Falls back to printing when no bot is configured."""
from __future__ import annotations

import html
import os
from collections import defaultdict
from datetime import date

import requests

from .analyzer import SEVERITY, Analysis, alert_level

EMOJI = {"OK": "🟢", "PROJECTED": "🔵", "WARN": "🟡", "CRITICAL": "🟠", "OVER": "🔴"}
TELEGRAM_LIMIT = 4000  # Telegram max is 4096 characters per message


def fmt(x: float) -> str:
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    if float(x).is_integer():
        return f"{x:.0f}"
    return f"{x:.2f}"


def bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def _line(a: Analysis, level: str) -> str:
    r = a.record
    head = f"{EMOJI.get(level, '⚪')} <b>{level}</b> {html.escape(r.provider)} · {html.escape(r.service)} · {html.escape(r.metric)}"
    if r.limit > 0:
        body = f"   {fmt(r.used)} / {fmt(r.limit)} {html.escape(r.unit)} ({a.percent:.0f}%)"
    else:
        body = f"   {fmt(r.used)} {html.escape(r.unit)} used — free limit is 0"
    if a.will_exceed and a.projected is not None:
        body += f"\n   📈 Projected {fmt(a.projected)} by month end"
        if a.limit_date:
            body += f" — limit hit around {a.limit_date:%d %b}"
    return f"{head}\n{body}"


def format_alert(items: list[tuple[Analysis, str]], today: date) -> str:
    items = sorted(items, key=lambda it: -SEVERITY.get(it[1], 0))
    lines = [f"☁️ <b>Free Tier Alert</b> — {today:%d %b %Y}", ""]
    lines += [_line(a, level) for a, level in items]
    lines += ["", "Tip: stop or delete the resource, or check the dashboard."]
    return "\n".join(lines)


def format_summary(analyses: list[Analysis], today: date) -> str:
    groups: dict[str, list[Analysis]] = defaultdict(list)
    for a in analyses:
        groups[a.record.provider].append(a)
    lines = [f"📊 <b>Weekly Free Tier Summary</b> — {today:%d %b %Y}"]
    for provider in sorted(groups):
        lines += ["", f"<b>{html.escape(provider.upper())}</b>"]
        for a in sorted(groups[provider], key=lambda x: -x.percent):
            r = a.record
            pct = min(a.percent, 999)
            limit = fmt(r.limit) if r.limit > 0 else "0"
            lines.append(
                f"{EMOJI.get(a.status, '⚪')} {bar(pct)} {pct:>3.0f}%  {html.escape(r.service)} · "
                f"{html.escape(r.metric)} ({fmt(r.used)}/{limit} {html.escape(r.unit)})"
            )
    worst = [a for a in analyses if alert_level(a)]
    lines += ["", f"{len(worst)} metric(s) need attention." if worst else "✅ Everything is inside the free tier."]
    return "\n".join(lines)


def format_errors(errors: list[tuple[str, str]], today: date) -> str:
    lines = [f"⚠️ <b>Tracker could not read some clouds</b> — {today:%d %b %Y}", ""]
    lines += [f"• <b>{html.escape(name)}</b>: {html.escape(msg[:300])}" for name, msg in errors]
    return "\n".join(lines)


def _chunks(text: str, size: int = TELEGRAM_LIMIT):
    buf = ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > size and buf:
            yield buf
            buf = ""
        buf += line + "\n"
    if buf:
        yield buf


class Notifier:
    def __init__(self, token: str | None, chat_id: str | None, dry_run: bool = False):
        self.token = token
        self.chat_id = chat_id
        self.dry_run = dry_run

    @classmethod
    def from_env(cls, dry_run: bool = False) -> "Notifier":
        return cls(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"), dry_run)

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id) and not self.dry_run

    def send(self, text: str) -> bool:
        """Returns True only if the message really reached Telegram."""
        if not self.enabled:
            print("\n--- notification (console only; Telegram not configured or dry-run) ---")
            print(html.unescape(text.replace("<b>", "").replace("</b>", "")))
            print("--- end ---\n")
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        for part in _chunks(text):
            resp = requests.post(url, json={
                "chat_id": self.chat_id, "text": part,
                "parse_mode": "HTML", "disable_web_page_preview": True,
            }, timeout=15)
            if resp.status_code != 200:
                raise RuntimeError(f"Telegram error {resp.status_code}: {resp.text[:200]}")
        return True
