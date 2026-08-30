"""SQLite şeması ve yazma işlemleri. Şema PROJECT.md §5'ten birebir."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sources.base import Item

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "digest.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  url_hash    TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  url         TEXT NOT NULL,
  category    TEXT NOT NULL,
  sources     TEXT NOT NULL,
  score       REAL NOT NULL,
  summary_tr  TEXT,
  why_tr      TEXT,
  published_at TEXT NOT NULL,
  first_seen  TEXT NOT NULL,
  digest_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_digest_date ON items(digest_date);

CREATE TABLE IF NOT EXISTS runs (
  run_at        TEXT PRIMARY KEY,
  items_raw     INTEGER,
  items_kept    INTEGER,
  failed_sources TEXT,
  llm_cost_usd  REAL,
  api_cost_usd  REAL
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_items(conn: sqlite3.Connection, items: list[Item]) -> tuple[int, int]:
    """Item'ları yazar. Var olan url_hash için `sources` listesi birleştirilir.

    Döner: (yeni kayıt, güncellenen kayıt)
    NOT: buradaki `score` ham metriktir. Faz 3'te skorlama formülü bunun üzerine yazacak.
    """
    now = datetime.now(timezone.utc).isoformat()
    new = updated = 0
    for it in items:
        row = conn.execute(
            "SELECT sources, score FROM items WHERE url_hash = ?", (it.url_hash,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO items (url_hash, title, url, category, sources, score,"
                " published_at, first_seen, digest_date) VALUES (?,?,?,?,?,?,?,?,NULL)",
                (it.url_hash, it.title, it.url, it.category, json.dumps([it.source]),
                 it.raw_score, it.published_at.isoformat(), now),
            )
            new += 1
        else:
            srcs = json.loads(row["sources"])
            if it.source not in srcs:
                srcs.append(it.source)
            conn.execute(
                "UPDATE items SET sources = ?, score = ? WHERE url_hash = ?",
                (json.dumps(srcs), max(row["score"], it.raw_score), it.url_hash),
            )
            updated += 1
    conn.commit()
    return new, updated


def record_run(conn: sqlite3.Connection, *, items_raw: int, items_kept: int,
               failed_sources: list[str], llm_cost_usd: float = 0.0,
               api_cost_usd: float = 0.0) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO runs (run_at, items_raw, items_kept, failed_sources,"
        " llm_cost_usd, api_cost_usd) VALUES (?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), items_raw, items_kept,
         json.dumps(failed_sources), llm_cost_usd, api_cost_usd),
    )
    conn.commit()
