"""Command line entry point.

  python -m tracker run            fetch usage, save it, alert if needed
  python -m tracker run --summary  also send the weekly summary now
  python -m tracker seed --days 30 fill 30 days of mock history (for the dashboard)
  python -m tracker show           print the latest saved numbers
  python -m tracker test-telegram  send a test message to your Telegram bot
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .analyzer import Analysis, alert_level, analyze
from .config import database_path, enabled_providers, load_config
from .models import UsageRecord
from .notifier import EMOJI, Notifier, fmt, format_alert, format_errors, format_summary
from .providers import get_provider
from .storage import Storage

log = logging.getLogger("tracker")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def resolve_today(cfg: dict, override: str | None) -> date:
    if override:
        return date.fromisoformat(override)
    return datetime.now(ZoneInfo(cfg.get("timezone", "UTC"))).date()


def collect(cfg: dict, today: date, names: list[str]):
    records: list[UsageRecord] = []
    errors: list[tuple[str, str]] = []
    for name in names:
        try:
            got = get_provider(name, cfg, today).fetch()
            log.info("%-7s -> %d metric(s)", name, len(got))
            records.extend(got)
        except Exception as exc:  # one broken cloud must not stop the others
            log.warning("%-7s -> FAILED: %s", name, exc)
            errors.append((name, f"{type(exc).__name__}: {exc}"))
    return records, errors


def process(cfg: dict, storage: Storage, records: list[UsageRecord], today: date) -> list[Analysis]:
    warn = float(cfg.get("alert_threshold_pct", 80))
    crit = float(cfg.get("critical_threshold_pct", 95))
    out = []
    for r in records:
        a = analyze(r, today, warn, crit, history=storage.history(r, today))
        storage.save(today, a)
        out.append(a)
    return out


def print_table(analyses: list[Analysis]) -> None:
    if not analyses:
        print("No metrics collected.")
        return
    print(f"\n{'':2} {'PROVIDER':<11} {'SERVICE':<16} {'METRIC':<30} {'USED / LIMIT':>32} {'%':>6}  FORECAST")
    for a in sorted(analyses, key=lambda x: -x.percent):
        r = a.record
        used = f"{fmt(r.used)} / {fmt(r.limit)} {r.unit}"
        forecast = ""
        if a.will_exceed:
            forecast = f"→ {fmt(a.projected)}"
            if a.limit_date:
                forecast += f" (limit ~{a.limit_date:%d %b})"
        print(f"{EMOJI.get(a.status, ' ')} {r.provider[:11]:<11} {r.service[:16]:<16} "
              f"{r.metric[:30]:<30} {used[:32]:>32} {a.percent:>5.0f}%  {forecast}")
    print()


def cmd_run(args, cfg) -> int:
    today = resolve_today(cfg, args.date)
    names = enabled_providers(cfg)
    if not names:
        print("No providers enabled. Set 'enabled: true' in config/limits.yaml or TRACKER_PROVIDERS=mock")
        return 1

    log.info("Run for %s, providers: %s", today, ", ".join(names))
    storage = Storage(database_path(cfg))
    notifier = Notifier.from_env(dry_run=args.dry_run)
    try:
        records, errors = collect(cfg, today, names)
        analyses = process(cfg, storage, records, today)
        print_table(analyses)

        month = f"{today:%Y-%m}"
        pending = []
        for a in analyses:
            level = alert_level(a)
            if level and not storage.alert_sent(month, a.record, level):
                pending.append((a, level))

        if pending:
            log.info("%d new alert(s)", len(pending))
            if notifier.send(format_alert(pending, today)):
                for a, level in pending:  # remember only alerts that really reached you
                    storage.mark_alert(month, a.record, level)
        else:
            log.info("No new alerts")

        if errors:
            notifier.send(format_errors(errors, today))

        summary_day = str(cfg.get("summary_weekday", "monday")).lower()
        if args.summary or (summary_day in WEEKDAYS and today.weekday() == WEEKDAYS.index(summary_day)):
            notifier.send(format_summary(analyses, today))
    finally:
        storage.close()

    return 1 if errors and not analyses else 0


def cmd_seed(args, cfg) -> int:
    """Build history with mock data so charts and trend forecasts have something to show."""
    today = resolve_today(cfg, args.date)
    storage = Storage(database_path(cfg))
    try:
        for i in range(args.days - 1, -1, -1):
            day = today - timedelta(days=i)
            records = get_provider("mock", cfg, day).fetch()
            process(cfg, storage, records, day)
        print(f"Seeded {args.days} day(s) of mock data into {database_path(cfg)}")
    finally:
        storage.close()
    return 0


def cmd_show(args, cfg) -> int:
    storage = Storage(database_path(cfg))
    try:
        rows = storage.latest()
    finally:
        storage.close()
    if not rows:
        print("No data yet. Run: python -m tracker run")
        return 1
    print(f"Latest data: {rows[0]['day']}\n")
    for r in rows:
        print(f"{EMOJI.get(r['status'], ' ')} {r['provider']:<11} {r['service'][:16]:<16} "
              f"{r['metric'][:30]:<30} {fmt(r['used'])} / {fmt(r['limit_value'])} {r['unit']} "
              f"({r['percent']:.0f}%)")
    return 0


def cmd_test_telegram(args, cfg) -> int:
    notifier = Notifier.from_env()
    if not notifier.enabled:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID first (see README, step 3).")
        return 1
    notifier.send("✅ <b>Free Tier Tracker</b> is connected. You'll get alerts here.")
    print("Test message sent. Check Telegram!")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tracker", description="Multi-cloud free tier tracker")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--config", help="path to limits.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="fetch usage, save, alert")
    run.add_argument("--dry-run", action="store_true", help="print alerts instead of sending")
    run.add_argument("--summary", action="store_true", help="send the summary now")
    run.add_argument("--date", help="pretend today is YYYY-MM-DD (testing)")
    run.set_defaults(func=cmd_run)

    seed = sub.add_parser("seed", help="fill history with mock data")
    seed.add_argument("--days", type=int, default=30)
    seed.add_argument("--date", help="last day to seed, YYYY-MM-DD")
    seed.set_defaults(func=cmd_seed)

    sub.add_parser("show", help="print latest saved data").set_defaults(func=cmd_show)
    sub.add_parser("test-telegram", help="send a test message").set_defaults(func=cmd_test_telegram)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    if not args.verbose:  # keep cloud SDK logs quiet
        for noisy in ("azure", "botocore", "urllib3", "google", "oci"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
    cfg = load_config(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
