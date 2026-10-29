from datetime import date

import pytest

from tracker import cli
from tracker.analyzer import analyze
from tracker.config import enabled_providers, load_config
from tracker.notifier import format_summary
from tracker.providers import ProviderError, get_provider
from tracker.storage import Storage


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACKER_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("TRACKER_PROVIDERS", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    return load_config()


def test_default_config_is_mock_only(cfg):
    assert enabled_providers(cfg) == ["mock"]


def test_env_override(monkeypatch):
    monkeypatch.setenv("TRACKER_PROVIDERS", "aws, gcp")
    assert sorted(enabled_providers(load_config())) == ["aws", "gcp"]


def test_mock_is_deterministic_and_grows(cfg):
    d1 = get_provider("mock", cfg, date(2026, 10, 10)).fetch()
    d1_again = get_provider("mock", cfg, date(2026, 10, 10)).fetch()
    d2 = get_provider("mock", cfg, date(2026, 10, 11)).fetch()
    assert [r.used for r in d1] == [r.used for r in d1_again]
    for a, b in zip(d1, d2):
        assert b.used >= a.used


def test_unknown_provider(cfg):
    with pytest.raises(ProviderError):
        get_provider("nope", cfg, date.today())


def test_storage_history_and_alert_dedupe(tmp_path, cfg):
    s = Storage(tmp_path / "s.db")
    recs = get_provider("mock", cfg, date(2026, 10, 5)).fetch()
    for r in recs:
        s.save(date(2026, 10, 5), analyze(r, date(2026, 10, 5)))
    assert s.history(recs[0], date(2026, 10, 6)) == [(date(2026, 10, 5), recs[0].used)]
    assert s.history(recs[0], date(2026, 11, 1)) == []          # new month -> fresh start
    assert not s.alert_sent("2026-10", recs[0], "WARN")
    s.mark_alert("2026-10", recs[0], "WARN")
    assert s.alert_sent("2026-10", recs[0], "WARN")
    s.close()


def test_full_run_and_seed(cfg, capsys):
    assert cli.main(["seed", "--days", "10", "--date", "2026-10-28"]) == 0
    assert cli.main(["run", "--dry-run", "--date", "2026-10-28"]) == 0
    out = capsys.readouterr().out
    assert "Free Tier Alert" in out
    assert cli.main(["show"]) == 0


def test_summary_text(cfg):
    today = date(2026, 10, 20)
    analyses = [analyze(r, today) for r in get_provider("mock", cfg, today).fetch()]
    text = format_summary(analyses, today)
    assert "MOCK-AWS" in text and "%" in text
