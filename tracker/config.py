"""Loads config/limits.yaml and applies environment-variable overrides."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "limits.yaml"


def load_config(path: str | os.PathLike | None = None) -> dict:
    path = Path(path or os.getenv("TRACKER_CONFIG") or DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    providers = cfg.setdefault("providers", {})
    for name in list(providers):
        providers[name] = providers[name] or {}

    # TRACKER_PROVIDERS=mock,aws  -> enables exactly these providers
    env = os.getenv("TRACKER_PROVIDERS", "").strip()
    if env:
        wanted = {p.strip().lower() for p in env.split(",") if p.strip()}
        for name in set(providers) | wanted:
            providers.setdefault(name, {})
            providers[name]["enabled"] = name in wanted
    return cfg


def enabled_providers(cfg: dict) -> list[str]:
    return [name for name, settings in cfg.get("providers", {}).items()
            if settings and settings.get("enabled")]


def database_path(cfg: dict) -> Path:
    p = Path(os.getenv("TRACKER_DB") or cfg.get("database", "data/usage.db"))
    return p if p.is_absolute() else ROOT / p
