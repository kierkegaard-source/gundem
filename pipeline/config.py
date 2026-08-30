"""config.yaml + .env yükleyici."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def load_config(path: str | None = None) -> dict:
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with cfg_path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg.setdefault("sources", {})
    cfg.setdefault("filters", {})
    cfg.setdefault("budget", {})
    cfg.setdefault("scoring", {})
    return cfg


def enabled_sources(cfg: dict) -> dict[str, dict]:
    return {k: v for k, v in cfg["sources"].items() if v.get("enabled")}


def secret(name: str) -> str | None:
    """Ortam değişkeni. Yoksa None — çağıran kaynak kendini kapatır."""
    val = os.environ.get(name)
    return val.strip() if val else None
