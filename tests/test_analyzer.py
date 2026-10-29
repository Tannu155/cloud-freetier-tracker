from datetime import date

from tracker.analyzer import alert_level, analyze, daily_rate, status_for
from tracker.models import UsageRecord


def rec(used, limit, cumulative=True, forecast=None):
    return UsageRecord("aws", "EC2", "hours", used, limit, "Hrs", cumulative, forecast)


def test_status_thresholds():
    assert status_for(rec(100, 750), 80, 95) == "OK"
    assert status_for(rec(600, 750), 80, 95) == "WARN"
    assert status_for(rec(720, 750), 80, 95) == "CRITICAL"
    assert status_for(rec(750, 750), 80, 95) == "OVER"


def test_zero_limit_means_any_usage_is_over():
    assert status_for(rec(0, 0), 80, 95) == "OK"
    assert status_for(rec(0.01, 0), 80, 95) == "OVER"


def test_projection_and_limit_date_from_average():
    # 10 days, 300 used -> 30/day -> 750 reached on day 25, month end = 300 + 30*21 = 930
    a = analyze(rec(300, 750), date(2026, 10, 10))
    assert a.status == "OK"
    assert round(a.projected) == 930
    assert a.limit_date == date(2026, 10, 25)
    assert a.will_exceed
    assert alert_level(a) == "PROJECTED"


def test_safe_metric_has_no_alert():
    a = analyze(rec(50, 750), date(2026, 10, 10))
    assert not a.will_exceed
    assert a.limit_date is None
    assert alert_level(a) is None


def test_trend_uses_recent_history():
    # nothing used for a week, then +50/day: month average (26.7) would underestimate
    history = [(date(2026, 10, d), max(0, 50.0 * (d - 7))) for d in range(1, 15)]
    rate = daily_rate(rec(400, 750), date(2026, 10, 15), history)
    assert rate == 50


def test_provider_forecast_wins():
    a = analyze(rec(100, 750, forecast=800), date(2026, 10, 10))
    assert a.projected == 800 and a.will_exceed


def test_gauge_metrics_are_not_projected():
    a = analyze(rec(4, 5, cumulative=False), date(2026, 10, 10))
    assert a.projected is None and a.status == "WARN"
